"""PanelAPIClient 响应解析测试。

`_call` 全部替换为假实现，不发网络请求。重点覆盖 QQ 返回结构意外时
不再抛裸 KeyError（前端只见 500），而是可读的 PanelAPIError。
"""

from typing import Any

import pytest

from nonebot_plugin_maestro.models import Panel
from nonebot_plugin_maestro.exceptions import PanelAPIError
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
