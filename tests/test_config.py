"""插件配置测试。

Config 是纯 pydantic 模型，直接实例化即可测——不需要 NoneBot 环境。
"""

import pytest
from pydantic import ValidationError

from nonebot_plugin_maestro.config import Config, exposure_problem


class TestDefaults:
    def test_zero_config_loads(self):
        """插件须支持零配置加载（发布规范要求）。"""
        config = Config()
        assert config.maestro_host == "127.0.0.1"
        assert config.maestro_port == 8100
        assert config.maestro_enabled is True

    def test_default_host_is_loopback(self):
        """默认只监听本机：WebUI 无鉴权，不应默认对外暴露。"""
        assert Config().maestro_host == "127.0.0.1"

    def test_default_port_avoids_nonebot(self):
        """默认端口须避开 NoneBot 的 8080，否则与 bot 服务抢占。"""
        assert Config().maestro_port != 8080


class TestOverrides:
    def test_accepts_custom_host_port(self):
        config = Config(maestro_host="0.0.0.0", maestro_port=9000)
        assert config.maestro_host == "0.0.0.0"
        assert config.maestro_port == 9000

    def test_coerces_port_from_string(self):
        """.env 里的值是字符串，pydantic 须能转成 int。"""
        config = Config.model_validate({"maestro_port": "8123"})
        assert config.maestro_port == 8123

    def test_can_be_disabled(self):
        assert Config(maestro_enabled=False).maestro_enabled is False

    @pytest.mark.parametrize("port", [0, -1, 65536, 99999])
    def test_rejects_out_of_range_port(self, port: int):
        with pytest.raises(ValidationError):
            Config(maestro_port=port)

    def test_rejects_non_numeric_port(self):
        with pytest.raises(ValidationError):
            Config.model_validate({"maestro_port": "not-a-port"})


class TestExposureEnforcement:
    """公网部署缺令牌时必须拒绝（WebUI 拒绝启动，bot 不受影响）。"""

    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
    def test_loopback_without_token_is_fine(self, host: str):
        """本机绑定保持零配置可用（发布规范）。"""
        assert exposure_problem(host, "") is None

    def test_exposed_with_token_is_fine(self):
        assert exposure_problem("0.0.0.0", "s3cret") is None

    @pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "::", "example.com"])
    def test_exposed_without_token_is_rejected(self, host: str):
        """非回环绑定（IPv4/IPv6 通配、内网 IP、域名）空令牌一律拒绝。"""
        problem = exposure_problem(host, "")
        assert problem is not None
        assert "MAESTRO_TOKEN" in problem
