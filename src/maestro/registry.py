"""已连接机器人的客户端注册表。

用类封装取代模块级 dict：状态的读写入口集中，便于测试时替换实例。
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maestro.panel_client import PanelAPIClient


class BotRegistry:
    """bot id -> 面板 API 客户端。

    面板管理是纯 REST 操作，客户端只借 Bot 的鉴权能力、不依赖 WS 会话本身；
    但注册动作挂在 NoneBot 的连接钩子上，可保证只有真正连上的 bot 出现在
    WebUI 里（独立模式则在启动时直接按配置全量注册）。
    """

    def __init__(self) -> None:
        self._clients: dict[str, PanelAPIClient] = {}

    def __len__(self) -> int:
        return len(self._clients)

    def __contains__(self, bot_id: str) -> bool:
        return bot_id in self._clients

    def get(self, bot_id: str) -> "PanelAPIClient | None":
        """按 bot id 取客户端，不存在返回 None。"""
        return self._clients.get(bot_id)

    def items(self) -> list[tuple[str, "PanelAPIClient"]]:
        """返回 (bot_id, client) 列表快照，避免调用方遍历时被并发修改影响。"""
        return list(self._clients.items())

    def ids(self) -> list[str]:
        """返回已注册的 bot id 列表。"""
        return list(self._clients)

    def add(self, client: "PanelAPIClient") -> None:
        """登记一个客户端，键取其 bot.self_id。"""
        self._clients[client.bot.self_id] = client

    def register_by_id(self, bot_id: str) -> bool:
        """按 bot id 从配置构造并登记客户端。

        Returns:
            是否找到匹配的配置项。
        """
        from maestro.panel_client import PanelAPIClient

        for client in PanelAPIClient.all_from_config():
            if client.bot.self_id == bot_id:
                self._clients[bot_id] = client
                return True
        return False

    def register_all_from_config(self) -> None:
        """按 QQ_BOTS 配置全量登记（独立模式用，不需要 WS 连接）。"""
        from maestro.panel_client import PanelAPIClient

        for client in PanelAPIClient.all_from_config():
            self.add(client)

    def remove(self, bot_id: str) -> None:
        """移除客户端（bot 断开时调用）。"""
        self._clients.pop(bot_id, None)

    def clear(self) -> None:
        """清空注册表（服务关闭时调用）。"""
        self._clients.clear()
