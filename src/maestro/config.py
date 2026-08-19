"""WebUI 运行配置。

监听地址对两种启动方式（`python bot.py` 与 `python -m maestro`）通用。
"""

import os
from typing import ClassVar

from maestro.logger import get_logger

# 默认监听地址。有意避开 NoneBot 默认的 8080，
# 使 WebUI 与 bot 服务各占一个端口、可同时运行。
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8100


class WebUIConfig:
    """WebUI 监听地址解析。

    查找顺序：`.env` 中的 MAESTRO_HOST/MAESTRO_PORT -> 同名环境变量 -> 默认值。
    """

    HOST_KEY: ClassVar[str] = "MAESTRO_HOST"
    PORT_KEY: ClassVar[str] = "MAESTRO_PORT"

    @staticmethod
    def _nonebot_extra() -> dict[str, object]:
        """取 NoneBot 配置中的额外字段（`.env` 里的自定义项落在这里）。

        NoneBot 用 pydantic-settings 读 `.env`，**不会**写回 os.environ，
        所以只查 os.getenv 会读不到 `.env` 里的 MAESTRO_* 配置。
        未安装 nonebot 或尚未 init 时返回空字典。
        """
        try:
            import nonebot

            return nonebot.get_driver().config.model_extra or {}
        except (ImportError, ValueError):
            # ValueError: NoneBot 尚未 init
            return {}

    @classmethod
    def _pick(cls, key: str, default: str) -> str:
        """按 .env -> 环境变量 -> 默认值的顺序取值。"""
        val = cls._nonebot_extra().get(key.lower())
        if val is not None:
            return str(val)
        return os.getenv(key, default)

    @classmethod
    def bind(cls) -> tuple[str, int]:
        """返回 (host, port)。端口非法时告警并回退到默认值。"""
        host = cls._pick(cls.HOST_KEY, DEFAULT_HOST)
        raw_port = cls._pick(cls.PORT_KEY, str(DEFAULT_PORT))
        try:
            port = int(raw_port)
        except ValueError:
            get_logger().warning(
                f"{cls.PORT_KEY}={raw_port!r} 不是合法端口号，回退到 {DEFAULT_PORT}"
            )
            port = DEFAULT_PORT
        return host, port
