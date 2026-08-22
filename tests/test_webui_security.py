"""WebUI 安全策略测试。

SecurityPolicy 由 _setup() 在插件加载时注入配置；测试直接 configure，
覆盖三层防线：Host 白名单（防 DNS rebinding）、Origin 同源（防 CSRF）、
可选令牌（MAESTRO_TOKEN）。TestClient 的 base_url 决定 Host 头。
"""

import pytest
from test_routes import BOT_ID, FakeClient
from fastapi.testclient import TestClient

from nonebot_plugin_maestro.webui import app, registry, security_policy


@pytest.fixture
def client():
    registry.clear()
    registry.add(FakeClient())  # type: ignore[arg-type]
    security_policy.reset()
    with TestClient(app, base_url="http://127.0.0.1:8100") as c:
        yield c
    registry.clear()
    security_policy.reset()


class TestUnconfigured:
    def test_policy_inactive_until_configured(self, client: TestClient):
        """独立导入（未走 _setup）时不拦截：任意 Host（如 testserver）放行。"""
        assert client.get("/api/bots").status_code == 200


class TestHostAllowlist:
    def test_loopback_host_allowed(self, client: TestClient):
        security_policy.configure("127.0.0.1", 8100)
        assert client.get("/api/bots").status_code == 200

    def test_localhost_variant_allowed(self, client: TestClient):
        security_policy.configure("127.0.0.1", 8100)
        resp = client.get("/api/bots", headers={"Host": "localhost:8100"})
        assert resp.status_code == 200

    def test_foreign_host_rejected(self, client: TestClient):
        """DNS rebinding：恶意域名解析到 127.0.0.1，Host 头仍是该域名。"""
        security_policy.configure("127.0.0.1", 8100)
        resp = client.get("/api/bots", headers={"Host": "evil.com:8100"})
        assert resp.status_code == 403

    def test_non_loopback_binding_skips_host_check(self, client: TestClient):
        """对外暴露（0.0.0.0）时无法枚举合法域名，Host 校验让位。"""
        security_policy.configure("0.0.0.0", 8100)
        assert client.get("/api/bots").status_code == 200


class TestOriginCheck:
    def test_cross_site_origin_rejected(self, client: TestClient):
        """CSRF：跨站请求的 Origin 与 Host 必然不同。"""
        security_policy.configure("127.0.0.1", 8100)
        resp = client.get("/api/bots", headers={"Origin": "http://evil.com"})
        assert resp.status_code == 403

    def test_same_origin_allowed(self, client: TestClient):
        security_policy.configure("127.0.0.1", 8100)
        resp = client.get("/api/bots", headers={"Origin": "http://127.0.0.1:8100"})
        assert resp.status_code == 200

    def test_no_origin_allowed(self, client: TestClient):
        """非浏览器客户端（curl）不带 Origin，放行。"""
        security_policy.configure("127.0.0.1", 8100)
        assert client.get("/api/bots").status_code == 200


class TestTokenAuth:
    def test_empty_token_keeps_api_open(self, client: TestClient):
        """默认零配置不启用令牌（发布规范：零配置可用）。"""
        security_policy.configure("127.0.0.1", 8100)
        assert client.get("/api/bots").status_code == 200

    def test_missing_token_rejected(self, client: TestClient):
        security_policy.configure("127.0.0.1", 8100, token="s3cret")
        assert client.get("/api/bots").status_code == 401

    def test_wrong_token_rejected(self, client: TestClient):
        security_policy.configure("127.0.0.1", 8100, token="s3cret")
        resp = client.get("/api/bots", headers={"X-Maestro-Token": "nope"})
        assert resp.status_code == 401

    def test_correct_token_accepted(self, client: TestClient):
        security_policy.configure("127.0.0.1", 8100, token="s3cret")
        resp = client.get("/api/bots", headers={"X-Maestro-Token": "s3cret"})
        assert resp.status_code == 200

    def test_token_guards_api_only(self, client: TestClient):
        """令牌只护 /api/*：页面与静态资源须能打开，前端才有机会引导输入。"""
        security_policy.configure("127.0.0.1", 8100, token="s3cret")
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        panels = client.get(f"/api/bots/{BOT_ID}/panels", params={"scope": "group"})
        assert panels.status_code == 401
