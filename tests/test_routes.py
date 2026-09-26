"""WebUI 路由测试。

全部走假客户端——面板写接口会真实修改线上面板且不可逆，
CI 中绝不能打真实 API。
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from nonebot_plugin_maestro.webui import app, registry, write_throttler
from nonebot_plugin_maestro.models import BotProfile, PanelRecord, PanelListResponse
from nonebot_plugin_maestro.exceptions import PanelAPIError
from nonebot_plugin_maestro.validation import (
    MAX_ITEMS,
    DESC_MAX_WIDTH,
    NAME_MAX_WIDTH,
    REMARK_MAX_LENGTH,
    MAX_PANELS_PER_BOT,
)

BOT_ID = "102072450"


def make_record(panel_id: str = "p_test", items: list[dict] | None = None) -> dict:
    return {
        "panel_id": panel_id,
        "scope": "group",
        "target_type": "all",
        "panel": {"items": items or [], "remark": "备注", "version": 0},
        "created_at": "2026-08-19T17:14:59+08:00",
        "updated_at": "2026-08-19T17:14:59+08:00",
        "version": 1,
    }


class FakeBot:
    def __init__(self, self_id: str) -> None:
        self.self_id = self_id


class FakeClient:
    """记录调用参数的假客户端，不发任何网络请求。"""

    def __init__(self, self_id: str = BOT_ID) -> None:
        self.bot = FakeBot(self_id)
        self.calls: list[tuple[str, tuple, dict]] = []
        self.raise_on: str | None = None
        self.raise_limit: int | None = None
        self.panel_total = 0

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))
        if self.raise_on == name:
            raise PanelAPIError(
                status_code=400,
                code=30013,
                message="超出数量限制",
                limit=self.raise_limit,
            )

    async def get_me(self) -> BotProfile:
        self._record("get_me")
        return BotProfile(id="user-id", username="小桜铃")

    async def list_panels(
        self, scope: str, *, cursor: str = "", limit: int = 20
    ) -> PanelListResponse:
        self._record("list_panels", scope, cursor=cursor, limit=limit)
        return PanelListResponse.model_validate(
            {"records": [make_record()], "is_end": True}
        )

    async def count_panels(self) -> int | None:
        """面板总数。默认 0（未达上限），测试可改 panel_total 模拟配额满；
        置 None 模拟统计失败（网络异常等），此时预检必须放行。"""
        self._record("count_panels")
        return self.panel_total

    async def create_panel(self, scope: str, panel: Any, **kwargs: Any) -> str:
        self._record("create_panel", scope, panel, **kwargs)
        return "p_new"

    async def get_panel(self, panel_id: str) -> PanelRecord:
        self._record("get_panel", panel_id)
        return PanelRecord.model_validate(make_record(panel_id))

    async def update_panel(self, panel_id: str, panel: Any) -> int:
        self._record("update_panel", panel_id, panel)
        return 2

    async def delete_panel(self, panel_id: str) -> None:
        self._record("delete_panel", panel_id)

    async def update_panel_target(self, panel_id: str, op: str, **kwargs: Any) -> None:
        self._record("update_panel_target", panel_id, op, **kwargs)


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def client(fake_client: FakeClient):
    """注册假客户端并提供 TestClient；测试结束清空注册表与限速桶。"""
    registry.clear()
    write_throttler.reset()
    registry.add(fake_client)  # type: ignore[arg-type]
    with TestClient(app) as c:
        yield c
    registry.clear()
    write_throttler.reset()


class TestIndex:
    def test_serves_html(self, client: TestClient):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_references_external_assets(self, client: TestClient):
        """前端已拆为独立文件，index 不应再内嵌 style/script。"""
        body = client.get("/").text
        assert "/static/app.css" in body
        assert "/static/app.js" in body

    def test_app_js_precedes_alpine(self, client: TestClient):
        """app.js 必须排在 Alpine 之前：两者同为 defer，按文档顺序执行，
        若 Alpine 先跑则 maestroApp() 未定义、页面白屏。"""
        body = client.get("/").text
        assert body.index("/static/app.js") < body.index("alpinejs")

    def test_app_js_sends_token_header(self, client: TestClient):
        """app.js 统一走 apiFetch 并附加可选令牌头（配合 MAESTRO_TOKEN）。"""
        js = client.get("/static/app.js").text
        assert "X-Maestro-Token" in js
        assert "apiFetch" in js


class TestCaching:
    def test_index_no_cache(self, client: TestClient):
        """页面禁用启发式缓存：升级换文件后浏览器立即拿到新页面。"""
        resp = client.get("/")
        assert resp.headers["cache-control"] == "no-cache"

    def test_static_assets_no_cache(self, client: TestClient):
        resp = client.get("/static/app.js")
        assert resp.headers["cache-control"] == "no-cache"


class TestOpenApi:
    def test_version_tracks_package(self, client: TestClient):
        """openapi 版本号取自包元数据，不再手写、不随发版漂移。"""
        import nonebot_plugin_maestro

        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        assert resp.json()["info"]["version"] == nonebot_plugin_maestro.__version__

    def test_version_endpoint_tracks_package(self, client: TestClient):
        """/api/version 与包版本同源，供前端页脚显示。"""
        import nonebot_plugin_maestro

        resp = client.get("/api/version")
        assert resp.status_code == 200
        assert resp.json() == {"version": nonebot_plugin_maestro.__version__}

    def test_footer_version_not_hardcoded(self, client: TestClient):
        """页脚版本号改为动态渲染，HTML 里不得再写死 v0.x。"""
        html = client.get("/").text
        assert "sidebar-footer-version" in html
        assert "v0.1.0" not in html
        js = client.get("/static/app.js").text
        assert "/api/version" in js


class TestStatic:
    @pytest.mark.parametrize("name", ["app.css", "app.js", "index.html"])
    def test_serves_assets(self, client: TestClient, name: str):
        assert client.get(f"/static/{name}").status_code == 200


class TestListBots:
    def test_lists_registered(self, client: TestClient, fake_client: FakeClient):
        data = client.get("/api/bots").json()
        assert len(data["bots"]) == 1
        bot = data["bots"][0]
        assert bot["username"] == "小桜铃"
        # bot_id 是路由键（appId），与 /users/@me 的 id（用户 ID）不同
        assert bot["bot_id"] == BOT_ID
        assert bot["id"] == "user-id"

    def test_credential_failure_does_not_break_page(
        self, client: TestClient, fake_client: FakeClient
    ):
        """单个机器人凭证失效时仍返回 200，错误随该项下发。"""
        fake_client.raise_on = "get_me"
        resp = client.get("/api/bots")
        assert resp.status_code == 200
        bot = resp.json()["bots"][0]
        assert bot["username"] is None
        assert "超出数量限制" in bot["error"]

    def test_network_failure_does_not_break_page(
        self, client: TestClient, fake_client: FakeClient
    ):
        """网络层异常（NetworkError 等）同样只影响单项，不该让全页 500。"""

        async def boom(*args: Any, **kwargs: Any):
            raise RuntimeError("connection timed out")

        fake_client.get_me = boom  # type: ignore[assignment]
        resp = client.get("/api/bots")
        assert resp.status_code == 200
        bot = resp.json()["bots"][0]
        assert bot["username"] is None
        assert "connection timed out" in bot["error"]

    def test_empty_registry(self, client: TestClient):
        registry.clear()
        assert client.get("/api/bots").json() == {"bots": []}


class TestPanelRoutes:
    def test_list_panels(self, client: TestClient, fake_client: FakeClient):
        resp = client.get(f"/api/bots/{BOT_ID}/panels", params={"scope": "group"})
        assert resp.status_code == 200
        assert len(resp.json()["records"]) == 1
        assert fake_client.calls[0][0] == "list_panels"

    def test_list_panels_rejects_bad_scope(self, client: TestClient):
        resp = client.get(f"/api/bots/{BOT_ID}/panels", params={"scope": "guild"})
        assert resp.status_code == 422

    @pytest.mark.parametrize("limit", [0, -1, 51, 9999])
    def test_list_panels_rejects_out_of_range_limit(
        self, client: TestClient, limit: int
    ):
        """limit 越界在本地拦成 422，不透传 QQ API 消耗配额。"""
        resp = client.get(
            f"/api/bots/{BOT_ID}/panels", params={"scope": "group", "limit": limit}
        )
        assert resp.status_code == 422

    def test_list_panels_accepts_limit_upper_bound(self, client: TestClient):
        """limit=50 是合法边界，须放行。"""
        resp = client.get(
            f"/api/bots/{BOT_ID}/panels", params={"scope": "group", "limit": 50}
        )
        assert resp.status_code == 200

    def test_list_panels_requires_scope(self, client: TestClient):
        assert client.get(f"/api/bots/{BOT_ID}/panels").status_code == 422

    def test_unknown_bot_returns_404(self, client: TestClient):
        resp = client.get("/api/bots/unknown/panels", params={"scope": "group"})
        assert resp.status_code == 404

    def test_create_panel(self, client: TestClient, fake_client: FakeClient):
        resp = client.post(
            f"/api/bots/{BOT_ID}/panels",
            json={
                "scope": "group",
                "panel": {"items": [], "remark": "r"},
                "target_type": "all",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"panel_id": "p_new"}

    def test_create_panel_validates_body(self, client: TestClient):
        """超宽 desc 应在本地被拦下，不消耗 10 QPM 的写配额。"""
        resp = client.post(
            f"/api/bots/{BOT_ID}/panels",
            json={
                "scope": "group",
                "panel": {
                    "items": [
                        {
                            "name": "转换",
                            "desc": "解析哔哩哔哩视频，转换为MP3或FLAC格式音频",
                            "type": "command",
                        }
                    ]
                },
            },
        )
        assert resp.status_code == 422

    def test_get_panel(self, client: TestClient):
        resp = client.get(f"/api/bots/{BOT_ID}/panels/p_x")
        assert resp.status_code == 200
        assert resp.json()["panel_id"] == "p_x"

    def test_update_panel(self, client: TestClient):
        resp = client.put(
            f"/api/bots/{BOT_ID}/panels/p_x",
            json={"items": [], "remark": "改过"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"version": 2}

    def test_delete_panel(self, client: TestClient, fake_client: FakeClient):
        resp = client.delete(f"/api/bots/{BOT_ID}/panels/p_x")
        assert resp.status_code == 200
        assert ("delete_panel", ("p_x",), {}) in fake_client.calls

    def test_update_target_uses_body_not_query(
        self, client: TestClient, fake_client: FakeClient
    ):
        """op 走请求体：曾因作为标量参数被 FastAPI 当 query 而必然 422。"""
        resp = client.put(
            f"/api/bots/{BOT_ID}/panels/p_x/target",
            json={"op": "add", "group_openids": ["g1"]},
        )
        assert resp.status_code == 200
        assert fake_client.calls[0][0] == "update_panel_target"

    def test_update_target_rejects_bad_op(self, client: TestClient):
        resp = client.put(
            f"/api/bots/{BOT_ID}/panels/p_x/target", json={"op": "remove"}
        )
        assert resp.status_code == 422


class TestPanelQuota:
    """面板总数上限 20（账号级，跨全部 scope 合计）须在本地拦下。

    QQ 侧超限返回 code=30013「超出数量限制」，而该码同时用于字段显示宽度
    超限——照搬给用户会把人引向删减指令项，方向完全相反。
    """

    def test_create_rejected_at_quota(
        self, client: TestClient, fake_client: FakeClient
    ):
        fake_client.panel_total = MAX_PANELS_PER_BOT
        resp = client.post(
            f"/api/bots/{BOT_ID}/panels",
            json={"scope": "group", "panel": {"items": [], "remark": ""}},
        )
        assert resp.status_code == 409
        assert str(MAX_PANELS_PER_BOT) in resp.json()["detail"]
        # 必须在下单前拦住，不能真的建出第 21 个面板
        assert not [c for c in fake_client.calls if c[0] == "create_panel"]

    def test_quota_precheck_runs_after_throttle(
        self, client: TestClient, fake_client: FakeClient
    ):
        """限速令牌先取、预检后做：预检每次要打 4 个读接口。

        放在限速之前会让本地限速管不到它，而读配额只有 30 QPM、还要被 UI
        的列表加载共用——打满后 UI 显示空列表，比多花一个写令牌糟得多。
        因此 409 是要消耗写令牌的，这里把这个顺序固定下来。
        """
        fake_client.panel_total = MAX_PANELS_PER_BOT
        for _ in range(10):
            resp = client.post(
                f"/api/bots/{BOT_ID}/panels",
                json={"scope": "group", "panel": {"items": [], "remark": ""}},
            )
            if resp.status_code == 429:
                break
        else:
            pytest.fail("连发写请求始终未触发限速，说明预检跑在取令牌之前")

        # 限速是暂时的：等令牌桶回填后仍能拿到配额 409（而不是一直 429）
        write_throttler.reset()
        fake_client.panel_total = MAX_PANELS_PER_BOT
        assert (
            client.post(
                f"/api/bots/{BOT_ID}/panels",
                json={"scope": "group", "panel": {"items": [], "remark": ""}},
            ).status_code
            == 409
        )

    def test_create_allowed_below_quota(
        self, client: TestClient, fake_client: FakeClient
    ):
        fake_client.panel_total = MAX_PANELS_PER_BOT - 1
        resp = client.post(
            f"/api/bots/{BOT_ID}/panels",
            json={"scope": "group", "panel": {"items": [], "remark": ""}},
        )
        assert resp.status_code == 200


class TestPanelQuotaPrecheckFailure:
    """预检只是为了让超限报错更好懂，本身不该成为写操作的新依赖。

    改动前 create 只发 1 个请求；加权预检后若它失败会把创建路径的失败面
    放大 4 倍，且报出的错和「创建」毫无关系。
    """

    def test_count_failure_does_not_block_create(
        self, client: TestClient, fake_client: FakeClient
    ):
        fake_client.panel_total = None  # 统计失败
        resp = client.post(
            f"/api/bots/{BOT_ID}/panels",
            json={"scope": "group", "panel": {"items": [], "remark": ""}},
        )
        assert resp.status_code == 200
        assert [c for c in fake_client.calls if c[0] == "create_panel"]


class TestLimitsEndpoint:
    """上限下发：前端据此做实时提示，避免前后端各写一份数字而漂移。"""

    def test_returns_validation_limits(self, client: TestClient):
        data = client.get("/api/limits").json()
        assert data["name_max_width"] == NAME_MAX_WIDTH
        assert data["desc_max_width"] == DESC_MAX_WIDTH
        assert data["remark_max_length"] == REMARK_MAX_LENGTH
        assert data["max_items"] == MAX_ITEMS
        assert data["max_panels_per_bot"] == MAX_PANELS_PER_BOT

    def test_frontend_reads_limits_from_api(self, client: TestClient):
        """前端须真的去取，否则硬编码的数字又会与后端漂移。"""
        js = client.get("/static/app.js").text
        assert "/api/limits" in js


class TestWriteThrottle:
    def test_rapid_writes_get_429(self, client: TestClient, fake_client: FakeClient):
        """连写超桶容量后本地 429 + Retry-After，第 4 次不再打 QQ。"""
        payload = {
            "scope": "group",
            "panel": {"items": [], "remark": ""},
            "target_type": "all",
        }
        for _ in range(3):
            resp = client.post(f"/api/bots/{BOT_ID}/panels", json=payload)
            assert resp.status_code == 200
        fourth = client.post(f"/api/bots/{BOT_ID}/panels", json=payload)
        assert fourth.status_code == 429
        assert int(fourth.headers["Retry-After"]) >= 1
        creates = [c for c in fake_client.calls if c[0] == "create_panel"]
        assert len(creates) == 3

    def test_reads_not_throttled(self, client: TestClient):
        """限速只作用于写接口，读接口不受影响。"""
        for _ in range(4):
            resp = client.get(f"/api/bots/{BOT_ID}/panels", params={"scope": "group"})
            assert resp.status_code == 200


class TestErrorHandler:
    def test_panel_api_error_becomes_4xx(
        self, client: TestClient, fake_client: FakeClient
    ):
        """QQ 侧业务错误须转成 4xx 并透传 message，而非 500 + traceback。"""
        fake_client.raise_on = "list_panels"
        resp = client.get(f"/api/bots/{BOT_ID}/panels", params={"scope": "group"})
        assert resp.status_code == 400
        body = resp.json()
        assert "超出数量限制" in body["detail"]
        assert body["code"] == 30013

    def test_limit_is_exposed_in_response(
        self, client: TestClient, fake_client: FakeClient
    ):
        """服务端回传的 limit 要在响应里透出，前端才能显示权威数值。"""
        fake_client.raise_on = "list_panels"
        fake_client.raise_limit = 20
        resp = client.get(f"/api/bots/{BOT_ID}/panels", params={"scope": "group"})
        assert resp.status_code == 400
        body = resp.json()
        assert body["limit"] == 20
        assert "20" in body["detail"]

    def test_limit_is_null_when_not_returned(
        self, client: TestClient, fake_client: FakeClient
    ):
        """没有该字段时给 null，不能凭空造一个数值。"""
        fake_client.raise_on = "list_panels"
        resp = client.get(f"/api/bots/{BOT_ID}/panels", params={"scope": "group"})
        assert resp.json()["limit"] is None

    def test_5xx_from_qq_becomes_502(self, client: TestClient, fake_client: FakeClient):
        """QQ 侧 5xx 是上游故障，归一为 502 而非伪装成客户端错误。"""

        async def boom(*args: Any, **kwargs: Any):
            raise PanelAPIError(status_code=502, message="网关错误")

        fake_client.list_panels = boom  # type: ignore[assignment]
        resp = client.get(f"/api/bots/{BOT_ID}/panels", params={"scope": "group"})
        assert resp.status_code == 502
