"""WebUIServer 启动/关停测试。

重点覆盖端口占用路径：曾经端口被占用时，uvicorn 会在 serve() 任务内
`sys.exit(STARTUP_FAILURE)`，该 SystemExit 冒泡穿过事件循环、连带掀翻
宿主 bot，且启动日志仍打「已启动」掩盖失败。现改为预绑定 socket，占用时
在此同步收到普通 OSError，如实报错并跳过启动，宿主 bot 不受影响。
"""

import socket

import pytest

from nonebot_plugin_maestro.webui import WebUIServer, app


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestBindSocket:
    def test_returns_bound_socket(self):
        port = _free_port()
        server = WebUIServer(app, "127.0.0.1", port)
        sock = server._bind_socket()
        try:
            assert sock.getsockname()[1] == port
        finally:
            sock.close()


class TestStartFailure:
    async def test_port_conflict_does_not_crash(self, monkeypatch: pytest.MonkeyPatch):
        """绑定失败时 start() 须静默返回，绝不向上抛（曾以 SystemExit 掀翻宿主）。"""
        server = WebUIServer(app, "127.0.0.1", 8100)

        def boom() -> socket.socket:
            raise OSError(48, "Address already in use")

        monkeypatch.setattr(server, "_bind_socket", boom)
        await server.start()  # 不抛异常

        # 未创建后台任务与服务器实例
        assert server._task is None
        assert server._server is None

    async def test_stop_is_safe_when_never_started(self):
        """启动失败后 on_shutdown 仍会调 stop()，此时不应报错。"""
        server = WebUIServer(app, "127.0.0.1", 8100)
        await server.stop()  # 不抛异常


class TestStartStopRoundTrip:
    async def test_starts_then_stops_cleanly(self):
        """预绑定 socket 应被 uvicorn 的 sockets 分支接受，关停干净收尾。"""
        port = _free_port()
        server = WebUIServer(app, "127.0.0.1", port)
        await server.start()
        assert server._task is not None
        assert server._server is not None
        try:
            await server.stop()
            assert server._task.done()
        finally:
            # 兜底：即便断言失败也请求退出，避免悬挂任务
            if server._server is not None:
                server._server.should_exit = True
