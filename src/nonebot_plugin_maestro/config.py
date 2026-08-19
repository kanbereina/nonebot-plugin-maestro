"""插件配置。

用 pydantic 模型 + `nonebot.get_plugin_config` 读取，取代手工解析
`driver.config.model_extra`：后者是绕过 NoneBot 配置系统的写法，
且拿不到类型校验。`.env` 中以 `MAESTRO_` 前缀配置。
"""

from pydantic import Field, BaseModel


class Config(BaseModel):
    """Maestro WebUI 配置。

    全部字段都有默认值——插件须支持零配置加载（发布规范要求）。
    """

    maestro_host: str = Field(
        default="127.0.0.1",
        description="WebUI 监听地址。默认仅本机可访问；"
        "改为 0.0.0.0 会对外暴露，届时必须自行提供鉴权",
    )
    # 默认 8100 而非 8080：避开 NoneBot 默认端口，使两者可同时运行
    maestro_port: int = Field(
        default=8100, ge=1, le=65535, description="WebUI 监听端口"
    )
    maestro_enabled: bool = Field(
        default=True,
        description="是否随 bot 启动 WebUI；设为 false 可在不卸载插件的前提下停用",
    )


def get_config() -> Config:
    """取插件配置（须在 `nonebot.init()` 之后调用）。"""
    import nonebot

    return nonebot.get_plugin_config(Config)
