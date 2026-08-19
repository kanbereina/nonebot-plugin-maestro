"""Maestro - QQ 官方机器人指令面板可视化管理插件。"""

from nonebot import get_driver
from nonebot.plugin import PluginMetadata
from nonebot.adapters import Bot as BaseBot

from nonebot_plugin_maestro.webui import WebUIServer, app, registry
from nonebot_plugin_maestro.config import Config, get_config
from nonebot_plugin_maestro.logger import get_logger
from nonebot_plugin_maestro.models import (
    Panel,
    PanelItem,
    BotProfile,
    PanelRecord,
    PanelListResponse,
    CreatePanelRequest,
    UpdateTargetRequest,
)
from nonebot_plugin_maestro.exceptions import PanelAPIError
from nonebot_plugin_maestro.panel_client import PanelAPIClient

__plugin_meta__ = PluginMetadata(
    name="Maestro",
    description="QQ 官方机器人指令面板可视化管理工具",
    usage=(
        "插件加载后会在本地端口启动 WebUI（默认 http://127.0.0.1:8100）。\n"
        "bot 连接成功后，在浏览器中即可查看与编辑该机器人的指令面板。\n\n"
        "配置项（.env）：\n"
        "  MAESTRO_HOST=127.0.0.1  # 监听地址\n"
        "  MAESTRO_PORT=8100       # 监听端口\n"
        "  MAESTRO_ENABLED=true    # 是否启用"
    ),
    type="application",
    homepage="https://github.com/kanbereina/Maestro",
    config=Config,
    # 仅支持 QQ 适配器：指令面板是 QQ OpenAPI 专有接口
    supported_adapters={"~qq"},
    extra={"author": "KanbeReina <kano.2525@qq.com>"},
)

__version__ = "0.1.0"

__all__ = [
    "BotProfile",
    "Config",
    "CreatePanelRequest",
    "Panel",
    "PanelAPIClient",
    "PanelAPIError",
    "PanelItem",
    "PanelListResponse",
    "PanelRecord",
    "UpdateTargetRequest",
    "WebUIServer",
    "app",
    "registry",
]


def _setup() -> None:
    """绑定 NoneBot 生命周期钩子，随 bot 启动 WebUI。

    在模块导入时执行——插件被 `load_plugin` 加载即完成注册。

    NoneBot 未初始化时直接返回：使本包的子模块（模型、校验等）可被
    独立导入用于测试或复用，而不强制调用方先 `nonebot.init()`。
    """
    try:
        config = get_config()
    except ValueError:
        # NoneBot has not been initialized
        return

    log = get_logger()

    if not config.maestro_enabled:
        log.info("Maestro WebUI 已通过 MAESTRO_ENABLED=false 停用")
        return

    driver = get_driver()
    server = WebUIServer(app, config.maestro_host, config.maestro_port)

    # 钩子参数必须标注为 nonebot.adapters.Bot 及其子类：
    # NoneBot 的 BotParam 按类型解析注入，object 之类的标注会被拒绝
    @driver.on_bot_connect
    async def _on_connect(bot: BaseBot) -> None:
        registry.register_by_id(bot.self_id)

    @driver.on_bot_disconnect
    async def _on_disconnect(bot: BaseBot) -> None:
        registry.remove(bot.self_id)

    @driver.on_startup
    async def _start_webui() -> None:
        await server.start()

    @driver.on_shutdown
    async def _stop_webui() -> None:
        await server.stop()
        registry.clear()


_setup()
