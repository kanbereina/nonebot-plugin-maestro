"""QQ 指令面板 API 客户端。

adapter-qq 未封装 /v2/panels 接口，此模块通过 Bot._request 直接调用。
"""

from typing import Any, Literal
from collections.abc import Sequence

import nonebot
from nonebot.drivers import Request
from nonebot.adapters.qq import Bot
from nonebot.adapters.qq import Adapter as QQAdapter
from nonebot.adapters.qq.exception import ActionFailed

from nonebot_plugin_maestro.models import (
    Panel,
    BotProfile,
    PanelRecord,
    PanelListResponse,
)
from nonebot_plugin_maestro.exceptions import PanelAPIError

# ==================== API 客户端 ====================


class PanelAPIClient:
    """QQ 指令面板 API 客户端（封装 Bot._request 调用）。"""

    def __init__(self, bot: "Bot") -> None:
        self.bot = bot
        # API base URL 由 adapter 根据 QQ_IS_SANDBOX 决定（全局配置）
        self._base_url = str(bot.adapter.get_api_base()).rstrip("/")

    @classmethod
    def from_config(cls, index: int = 0) -> "PanelAPIClient":
        """从 NoneBot 配置直接构造客户端，不需要活跃的 WS 连接。

        `driver.bots` 只在 WebSocket 握手成功或收到 webhook 后才有内容，
        而面板管理是纯 REST 操作——`Bot._request` / `get_access_token` 仅用到
        `adapter`（取 base URL、发请求）与 `bot_info`（appId/secret），不触碰
        `_session_id`。因此这里直接用配置里的 BotInfo 构造 Bot 借其鉴权能力。

        Args:
            index: 使用 QQ_BOTS 中第几个 bot（默认第一个）

        Raises:
            RuntimeError: QQ_BOTS 未配置或下标越界
        """
        adapter = nonebot.get_adapter(QQAdapter)
        bot_infos = adapter.qq_config.qq_bots
        if not bot_infos:
            raise RuntimeError(
                "QQ_BOTS 未配置，请在 .env 中填写\n"
                '示例: QQ_BOTS=\'[{"id":"...","token":"...","secret":"..."}]\''
            )
        if index >= len(bot_infos):
            raise RuntimeError(
                f"QQ_BOTS 只配置了 {len(bot_infos)} 个 bot，无法取下标 {index}"
            )

        bot_info = bot_infos[index]
        return cls(Bot(adapter, bot_info.id, bot_info))

    @classmethod
    def from_config_by_id(cls, bot_id: str) -> "PanelAPIClient | None":
        """按 appId（即 self_id）从配置构造单个客户端，未找到返回 None。

        供 on_bot_connect 钩子用：只构造匹配的那一个，不必
        all_from_config() 全量建完再丢弃其余。
        """
        adapter = nonebot.get_adapter(QQAdapter)
        for bot_info in adapter.qq_config.qq_bots:
            if bot_info.id == bot_id:
                return cls(Bot(adapter, bot_info.id, bot_info))
        return None

    @classmethod
    def all_from_config(cls) -> list["PanelAPIClient"]:
        """为 QQ_BOTS 中每个 bot 各建一个客户端，供多机器人卡片使用。"""
        adapter = nonebot.get_adapter(QQAdapter)
        if not adapter.qq_config.qq_bots:
            raise RuntimeError(
                "QQ_BOTS 未配置，请在 .env 中填写\n"
                '示例: QQ_BOTS=\'[{"id":"...","token":"...","secret":"..."}]\''
            )
        return [cls.from_config(i) for i in range(len(adapter.qq_config.qq_bots))]

    async def get_me(self) -> BotProfile:
        """查询当前机器人信息（GET /users/@me）。

        适配器已有 `Bot.me()` 打同一个 endpoint，但它用自带的 `User` 模型解析，
        实测会丢掉 `share_url`（群分享链接，有真实值）与 `welcome_msg`——
        pydantic 默认忽略未声明字段。卡片要展示分享链接，故走自己的 BotProfile。
        """
        resp = await self._call("GET", "/users/@me")
        return BotProfile.model_validate(resp)

    @property
    def base_url(self) -> str:
        """当前使用的 API base URL（沙箱或生产，由 QQ_IS_SANDBOX 决定）。"""
        return self._base_url

    def _make_request(self, method: str, path: str, **kwargs: Any) -> Any:
        """构造 nonebot Request。"""
        return Request(method, f"{self._base_url}{path}", **kwargs)

    async def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        """发起请求，并把适配器异常转成不依赖 nonebot 的 PanelAPIError。

        QQ 侧的业务错误（数量超限、面板不存在、场景不支持等）是调用方输入或
        账号状态问题，不该以 500 + traceback 暴露给前端。
        """
        try:
            return await self.bot._request(self._make_request(method, path, **kwargs))
        except ActionFailed as e:
            raise PanelAPIError(
                status_code=e.status_code,
                code=e.code,
                message=e.message,
                trace_id=e.trace_id,
            ) from e

    async def list_panels(
        self,
        scope: Literal["c2c", "group", "channel", "dm"],
        *,
        cursor: str = "",
        limit: int = 20,
    ) -> PanelListResponse:
        """查询指令面板列表（游标翻页）。

        Args:
            scope: 场景类型
            cursor: 翻页游标（首次请求传空字符串）
            limit: 每页数量（默认 20，最大 50）
        """
        params: dict[str, Any] = {"scope": scope, "limit": limit}
        if cursor:
            params["cursor"] = cursor

        resp = await self._call("GET", "/v2/panels", params=params)
        return PanelListResponse.model_validate(resp)

    async def create_panel(
        self,
        scope: Literal["c2c", "group", "channel", "dm"],
        panel: Panel,
        *,
        target_type: Literal["all", "specific"] = "all",
        user_openids: Sequence[str] = (),
        group_openids: Sequence[str] = (),
    ) -> str:
        """创建指令面板。

        Args:
            scope: 场景类型
            panel: 面板配置
            target_type: 应用范围（channel/dm 仅支持 all）
            user_openids: 用户 openid 列表（c2c+specific，单次最多 20）
            group_openids: 群 openid 列表（group+specific，单次最多 20）

        Returns:
            新创建的 panel_id
        """
        body: dict[str, Any] = {
            "scope": scope,
            "target_type": target_type,
            "panel": panel.model_dump(mode="json"),
        }
        if user_openids:
            body["user_openids"] = list(user_openids)
        if group_openids:
            body["group_openids"] = list(group_openids)

        resp = await self._call("POST", "/v2/panels", json=body)
        panel_id = resp.get("panel_id", "") if isinstance(resp, dict) else ""
        if not panel_id:
            # 响应结构意外时给可读错误，而非裸 KeyError 变 500
            raise PanelAPIError(status_code=502, message="QQ 响应缺少 panel_id 字段")
        return panel_id

    async def get_panel(self, panel_id: str) -> PanelRecord:
        """查询指令面板详情。"""
        resp = await self._call("GET", f"/v2/panels/{panel_id}")
        return PanelRecord.model_validate(resp)

    async def update_panel(self, panel_id: str, panel: Panel) -> int:
        """修改指令面板内容（不影响关联对象）。

        Returns:
            修改后的版本号
        """
        body = {"panel": panel.model_dump(mode="json")}
        resp = await self._call("PUT", f"/v2/panels/{panel_id}", json=body)
        new_version = resp.get("version") if isinstance(resp, dict) else None
        if not isinstance(new_version, int):
            raise PanelAPIError(status_code=502, message="QQ 响应缺少 version 字段")
        return new_version

    async def delete_panel(self, panel_id: str) -> None:
        """删除指令面板（不可逆）。"""
        await self._call("DELETE", f"/v2/panels/{panel_id}")

    async def update_panel_target(
        self,
        panel_id: str,
        op: Literal["add", "del"],
        *,
        user_openids: Sequence[str] = (),
        group_openids: Sequence[str] = (),
    ) -> None:
        """增删面板关联对象（c2c/group+specific 场景）。

        Args:
            panel_id: 面板 ID
            op: 操作类型（add/del）
            user_openids: 用户 openid 列表（c2c 场景，单次最多 20）
            group_openids: 群 openid 列表（group 场景，单次最多 20）
        """
        body: dict[str, Any] = {"op": op}
        if user_openids:
            body["user_openids"] = list(user_openids)
        if group_openids:
            body["group_openids"] = list(group_openids)

        await self._call("PUT", f"/v2/panels/{panel_id}/target", json=body)
