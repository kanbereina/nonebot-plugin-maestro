"""Maestro - NoneBot2 QQ 指令面板可视化管理工具。"""

from typing import TYPE_CHECKING, Any

__version__ = "0.1.0"

__all__ = [
    "BotProfile",
    "CreatePanelRequest",
    "Panel",
    "PanelAPIClient",
    "PanelItem",
    "PanelListResponse",
    "PanelRecord",
    "UpdateTargetRequest",
]

if TYPE_CHECKING:
    from maestro.panel_client import (
        BotProfile,
        CreatePanelRequest,
        Panel,
        PanelAPIClient,
        PanelItem,
        PanelListResponse,
        PanelRecord,
        UpdateTargetRequest,
    )


def __getattr__(name: str) -> Any:
    """惰性导出 panel_client 成员。

    panel_client 依赖 qq extra（nonebot-adapter-qq）。核心安装（仅 FastAPI）
    下 `import maestro` 不应报错，因此把导入推迟到真正访问这些名字时。
    """
    if name in __all__:
        from maestro import panel_client

        return getattr(panel_client, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
