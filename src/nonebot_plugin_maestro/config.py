"""插件配置。

用 pydantic 模型 + `nonebot.get_plugin_config` 读取，取代手工解析
`driver.config.model_extra`：后者是绕过 NoneBot 配置系统的写法，
且拿不到类型校验。`.env` 中以 `MAESTRO_` 前缀配置。
"""

from pydantic import Field, BaseModel

# 视为「仅本机」的绑定地址：Host 白名单按此判断，不在其中的地址都算对外暴露
LOOPBACK_BINDINGS = {"127.0.0.1", "localhost", "::1"}


def exposure_problem(host: str, token: str) -> str | None:
    """公网部署缺令牌时返回拒绝原因；本机绑定或已设令牌返回 None。

    WebUI 的写接口（含不可逆删除）没有账号体系，令牌是唯一的访问控制，
    空令牌的对外暴露一律拒绝启动。文案保持单行。
    """
    if host in LOOPBACK_BINDINGS or token:
        return None
    return (
        f"MAESTRO_HOST={host} 会把 WebUI 暴露到网络，"
        "必须设置 MAESTRO_TOKEN 后才能启动 WebUI。"
    )


class Config(BaseModel):
    """Maestro WebUI 配置。

    全部字段都有默认值——插件须支持零配置加载（发布规范要求）。
    """

    maestro_host: str = Field(
        default="127.0.0.1",
        description="WebUI 监听地址。默认仅本机可访问；改为非回环地址"
        "（如 0.0.0.0）会对外暴露，必须同时设置 MAESTRO_TOKEN，"
        "否则 WebUI 拒绝启动",
    )
    # 默认 8100 而非 8080：避开 NoneBot 默认端口，使两者可同时运行
    maestro_port: int = Field(
        default=8100, ge=1, le=65535, description="WebUI 监听端口"
    )
    maestro_enabled: bool = Field(
        default=True,
        description="是否随 bot 启动 WebUI；设为 false 可在不卸载插件的前提下停用",
    )
    maestro_token: str = Field(
        default="",
        description="API 访问令牌。设置后所有 /api/* 请求须携带"
        " X-Maestro-Token 头（WebUI 会自动引导输入）；"
        "对外暴露（非回环绑定）时必须设置，否则拒绝启动",
    )


def get_config() -> Config:
    """取插件配置（须在 `nonebot.init()` 之后调用）。"""
    import nonebot

    return nonebot.get_plugin_config(Config)
