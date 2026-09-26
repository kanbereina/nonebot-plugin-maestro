"""插件生命周期注册（`_setup`）测试。

重点覆盖「配置有问题时插件的行为」：曾因 pydantic 的 ValidationError 是
ValueError 的子类，被 `except ValueError: return`（本意是挡 NoneBot 未
初始化的那句 ValueError）一并吞掉——插件照报加载成功，WebUI 却静默不
启动，且一行日志都没有。配置写错必须留下痕迹。

不触发真实 nonebot 初始化：`_setup` 引用的符号都在包命名空间里，替换它们
即可覆盖全部分支；启动路径则替换掉 WebUIServer，避免真的起进程。
"""

from typing import Any

import pytest

from nonebot_plugin_maestro import _setup
from nonebot_plugin_maestro.config import Config


class _Recorder:
    """收集日志的 (level, message)，避免匹配渲染后的彩色文本。"""

    def __init__(self) -> None:
        self.entries: list[tuple[str, str]] = []

    def __call__(self, message: Any) -> None:
        record = message.record
        self.entries.append((record["level"].name, record["message"]))

    @property
    def errors(self) -> list[str]:
        return [m for level, m in self.entries if level == "ERROR"]

    def any_mentioning(self, needle: str) -> bool:
        return any(needle in m for _, m in self.entries)


@pytest.fixture
def setup_env(monkeypatch: pytest.MonkeyPatch):
    """可控的 _setup 环境：返回 (agents 记录, 日志收集器)。

    agents 非空即表示走到了「启动 WebUI」这一步。
    """
    from nonebot.log import logger

    import nonebot_plugin_maestro as pkg
    from nonebot_plugin_maestro import security_policy

    agents: list[tuple[Any, ...]] = []

    class FakeServer:
        """替代真实 WebUIServer：只落在测试里，绝不真的起进程。"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs
            agents.append((args, kwargs))

        async def start(self) -> None: ...

        async def stop(self) -> None: ...

    # _setup 通过 from ... import 直接引用包命名空间里的符号，
    # 必须 patch 包的属性，patch webui.* 不生效
    monkeypatch.setattr(pkg, "security_policy", security_policy)
    monkeypatch.setattr(pkg, "WebUIServer", FakeServer)

    # 若测试中途真的 configure 了，结束后恢复，避免污染其他测试
    monkeypatch.setattr(security_policy, "_configured", False)
    monkeypatch.setattr(security_policy, "_enforce_host", False)
    monkeypatch.setattr(security_policy, "_allowed_hosts", set())

    recorder = _Recorder()
    sink_id = logger.add(recorder, level="INFO")
    try:
        yield agents, recorder
    finally:
        logger.remove(sink_id)


def _patch_config(monkeypatch: pytest.MonkeyPatch, config: Config) -> None:
    import nonebot_plugin_maestro as pkg

    monkeypatch.setattr(pkg, "get_config", lambda: config)


def _patch_config_error(monkeypatch: pytest.MonkeyPatch, factory: Any) -> None:
    import nonebot_plugin_maestro as pkg

    monkeypatch.setattr(pkg, "get_config", factory)


class TestUninitialized:
    def test_returns_quietly_when_nonebot_not_initialized(self, setup_env):
        """NoneBot 未 init 时静默返回：子模块要能被独立导入（测试依赖此行为）。"""
        agents, recorder = setup_env
        monkeypatch = pytest.MonkeyPatch()
        try:
            import nonebot_plugin_maestro as pkg

            def not_initialized():
                raise ValueError("NoneBot has not been initialized.")

            monkeypatch.setattr(pkg, "get_driver", not_initialized)
            _setup()
        finally:
            monkeypatch.undo()

        assert agents == []
        # 未初始化是预期路径：不该打 ERROR
        assert recorder.errors == []


class TestInvalidConfig:
    """配置写错时必须留下日志，且不影响宿主 bot（只记录、不上抛）。"""

    def test_non_ascii_token_is_reported(self, setup_env, monkeypatch):
        """非 ASCII 令牌：校验失败要报出来，而不是静默不启动。"""
        agents, recorder = setup_env
        _patch_config_error(monkeypatch, lambda: Config(maestro_token="令牌abc"))
        _setup()  # 不抛

        assert agents == [], "配置无效时不该启动 WebUI"
        assert recorder.errors, "配置错误必须留下日志，不能静默"
        assert any("ASCII" in m for m in recorder.errors)

    def test_out_of_range_port_is_reported(self, setup_env, monkeypatch):
        """端口越界此前同样静默：修复覆盖的不只是令牌这一项。"""
        agents, recorder = setup_env
        _patch_config_error(monkeypatch, lambda: Config(maestro_port=99999))
        _setup()

        assert agents == []
        assert recorder.errors

    def test_unexpected_error_is_logged_and_swallowed(self, setup_env, monkeypatch):
        """非校验类的意外错误也只记录、不上抛，绝不掀翻宿主。"""

        def boom() -> Config:
            raise RuntimeError("配置系统炸了")

        agents, recorder = setup_env
        _patch_config_error(monkeypatch, boom)
        _setup()  # 不抛

        assert agents == []
        assert recorder.errors


class TestStartupGate:
    """配置有效时的启动开关与暴露检查（回归保护）。"""

    def test_disabled_does_not_start(self, setup_env, monkeypatch):
        agents, recorder = setup_env
        _patch_config(monkeypatch, Config(maestro_enabled=False))
        _setup()

        assert agents == [], "MAESTRO_ENABLED=false 时不该启动 WebUI"
        assert recorder.any_mentioning("停用")

    def test_exposed_without_token_is_refused(self, setup_env, monkeypatch):
        """公网绑定 + 空令牌：拒绝启动（写接口无账号体系）。"""
        agents, recorder = setup_env
        _patch_config(monkeypatch, Config(maestro_host="0.0.0.0", maestro_token=""))
        _setup()

        assert agents == []
        assert recorder.any_mentioning("MAESTRO_TOKEN")

    def test_valid_config_starts_webui(self, setup_env, monkeypatch):
        """合法配置：注入安全策略并构造 WebUIServer。"""
        from nonebot_plugin_maestro import security_policy

        agents, _ = setup_env
        _patch_config(
            monkeypatch,
            Config(maestro_host="127.0.0.1", maestro_port=8123, maestro_token="s3cret"),
        )
        _setup()

        assert len(agents) == 1, "配置有效时必须启动 WebUI"
        # 令牌必须真的注入策略：漏传会让鉴权静默失效
        assert security_policy._token == "s3cret"
        assert security_policy._token_bytes == b"s3cret"
        # WebUIServer(app, host, port)：host/port 按位置传入
        _, host, port = agents[0][0]
        assert host == "127.0.0.1"
        assert port == 8123
        assert security_policy._configured is True
