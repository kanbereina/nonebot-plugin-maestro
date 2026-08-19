"""PanelAPIError 测试。

该异常刻意不依赖 nonebot：适配器的 ActionFailed 在 panel_client 边界
被转换成它，使异常处理与 QQ 侧类型解耦。
"""

from nonebot_plugin_maestro.exceptions import PanelAPIError


class TestDescribe:
    def test_prefers_server_message(self):
        """优先透传服务端 message——实测 code 语义具误导性。"""
        err = PanelAPIError(status_code=400, code=30013, message="超出数量限制")
        desc = err.describe()
        assert "超出数量限制" in desc
        assert "30013" in desc

    def test_message_only(self):
        err = PanelAPIError(status_code=400, message="参数非法")
        assert err.describe() == "参数非法"

    def test_code_only(self):
        err = PanelAPIError(status_code=400, code=30016)
        assert "30016" in err.describe()

    def test_falls_back_to_status(self):
        """无 message 也无 code 时至少给出 HTTP 状态。"""
        err = PanelAPIError(status_code=502)
        assert "502" in err.describe()


class TestAttributes:
    def test_keeps_trace_id(self):
        """trace_id 来自 X-Tps-trace-ID 响应头，排查时需要。"""
        err = PanelAPIError(
            status_code=400, code=30013, message="超出数量限制", trace_id="abc123"
        )
        assert err.trace_id == "abc123"

    def test_is_exception(self):
        err = PanelAPIError(status_code=400, message="x")
        assert isinstance(err, Exception)
        assert str(err) == err.describe()

    def test_repr_contains_fields(self):
        err = PanelAPIError(
            status_code=400, code=30013, message="超出数量限制", trace_id="t1"
        )
        r = repr(err)
        assert "400" in r
        assert "30013" in r
        assert "t1" in r
