"""PanelAPIClient 响应解析测试。

`_call` 全部替换为假实现，不发网络请求。重点覆盖 QQ 返回结构意外时
不再抛裸 KeyError（前端只见 500），而是可读的 PanelAPIError。
"""

from typing import Any

import pytest
from nonebot.exception import NetworkError

from nonebot_plugin_maestro.models import Panel, PanelListResponse
from nonebot_plugin_maestro.exceptions import PanelAPIError
from nonebot_plugin_maestro.validation import MAX_PANELS_PER_BOT
from nonebot_plugin_maestro.panel_client import PanelAPIClient


def make_client(resp: Any) -> PanelAPIClient:
    """绕过 __init__（需要真实 Bot 做鉴权），只挂假的 _call。"""
    client = PanelAPIClient.__new__(PanelAPIClient)

    async def fake_call(method: str, path: str, **kwargs: Any) -> Any:
        return resp

    client._call = fake_call  # type: ignore[method-assign]
    return client


class TestCreatePanel:
    async def test_returns_panel_id(self):
        client = make_client({"panel_id": "p_new"})
        assert await client.create_panel("group", Panel()) == "p_new"

    async def test_missing_panel_id_raises_api_error(self):
        client = make_client({"unexpected": 1})
        with pytest.raises(PanelAPIError, match="panel_id"):
            await client.create_panel("group", Panel())

    async def test_non_dict_response_raises_api_error(self):
        client = make_client("oops")
        with pytest.raises(PanelAPIError, match="panel_id"):
            await client.create_panel("group", Panel())


class TestUpdatePanel:
    async def test_returns_version(self):
        client = make_client({"version": 3})
        assert await client.update_panel("p_x", Panel()) == 3

    async def test_missing_version_raises_api_error(self):
        client = make_client({})
        with pytest.raises(PanelAPIError, match="version"):
            await client.update_panel("p_x", Panel())


class TestCountPanels:
    """面板总数统计（写操作前的预检）。

    预检只为让超限报错更好懂，失败必须放行——否则 4 个额外读请求会把
    创建路径的失败面放大 4 倍，报出的错还和「创建」毫无关系。
    """

    def _counting_client(self) -> tuple[PanelAPIClient, list[tuple[str, int]]]:
        client = PanelAPIClient.__new__(PanelAPIClient)
        seen: list[tuple[str, int]] = []

        def record(panel_id: str) -> dict[str, Any]:
            return {
                "panel_id": panel_id,
                "scope": "group",
                "target_type": "all",
                "panel": {"items": [], "remark": "", "version": 0},
                "created_at": "2026-08-19T17:14:59+08:00",
                "updated_at": "2026-08-19T17:14:59+08:00",
                "version": 1,
            }

        async def fake_list(scope: str, *, cursor: str = "", limit: int = 20):
            seen.append((scope, limit))
            # 只有 group 有 3 个面板，其余为空
            records = [record(f"p{i}") for i in range(3)] if scope == "group" else []
            return PanelListResponse.model_validate(
                {"records": records, "is_end": True}
            )

        client.list_panels = fake_list  # type: ignore[method-assign]
        return client, seen

    async def test_sums_across_all_scopes(self):
        client, seen = self._counting_client()
        assert await client.count_panels() == 3
        # 四个场景都要查到：上限是账号级的，漏查一个就会低估总数
        assert sorted(s for s, _ in seen) == ["c2c", "channel", "dm", "group"]

    async def test_limit_brackets_panel_cap(self):
        """limit 必须同时满足两个方向，只断言上界是不够的。

        上界：不得超过列表接口的上限 50（将来调高 MAX_PANELS_PER_BOT 时
        也不能跟着越界）。下界：不得小于面板总数上限——limit 太小会把某个
        scope 的列表截断，总数被低估，配额 409 就永远不触发。
        """
        client, seen = self._counting_client()
        await client.count_panels()
        assert all(limit <= 50 for _, limit in seen)
        assert all(limit >= MAX_PANELS_PER_BOT for _, limit in seen)

    async def test_api_error_returns_none(self):
        """QQ 侧业务错误：返回 None 让调用方放行，而不是打断创建。"""
        client = PanelAPIClient.__new__(PanelAPIClient)

        async def boom(*args: Any, **kwargs: Any):
            raise PanelAPIError(status_code=400, code=30013, message="超出数量限制")

        client.list_panels = boom  # type: ignore[method-assign]
        assert await client.count_panels() is None

    async def test_malformed_response_returns_none(self):
        """QQ 返回结构意外（pydantic ValidationError）同样不该拖垮创建。

        这类异常不在 AdapterException 之下，靠 `except Exception` 兜住。
        """
        client = PanelAPIClient.__new__(PanelAPIClient)

        async def boom(*args: Any, **kwargs: Any):
            return PanelListResponse.model_validate({"unexpected": 1})

        client.list_panels = boom  # type: ignore[method-assign]
        assert await client.count_panels() is None

    async def test_network_error_returns_none(self):
        """驱动层异常（如 QQ 网关不可达）同样不该冒泡成 500。"""
        client = PanelAPIClient.__new__(PanelAPIClient)

        async def boom(*args: Any, **kwargs: Any):
            raise NetworkError("API request failed")

        client.list_panels = boom  # type: ignore[method-assign]
        assert await client.count_panels() is None
