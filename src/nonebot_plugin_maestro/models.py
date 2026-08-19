"""面板数据模型。

与 QQ OpenAPI /v2/panels 的请求/响应结构对应。不依赖 nonebot，
供 webui 路由与 panel_client 共用。
"""

from typing import Literal

from pydantic import Field, BaseModel, field_validator, model_validator

from nonebot_plugin_maestro.validation import (
    MAX_ITEMS,
    DESC_MAX_WIDTH,
    NAME_MAX_WIDTH,
    REMARK_MAX_LENGTH,
    check_width,
)


class PanelItem(BaseModel):
    """面板元素。

    name/desc 的长度按**显示宽度**校验（中文计 2），与服务端口径一致；
    详见 maestro.validation 的实测说明。
    """

    name: str = Field(description="元素名称（显示宽度最多 14，即 7 个汉字）")
    desc: str = Field(description="元素描述（显示宽度最多 30，即 15 个汉字）")
    type: Literal["command", "link"] = Field(description="元素类型")
    only_admin: bool = Field(default=False, description="是否仅管理员可见")
    link: str | None = Field(
        default=None, description="type=link 时的跳转 URL（必须 https）"
    )

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        check_width(v, NAME_MAX_WIDTH, "指令名称")
        return v

    @field_validator("desc")
    @classmethod
    def _check_desc(cls, v: str) -> str:
        check_width(v, DESC_MAX_WIDTH, "指令描述")
        return v

    @model_validator(mode="after")
    def _check_link(self) -> "PanelItem":
        if self.type == "link" and not (self.link or "").startswith("https://"):
            raise ValueError(
                f"链接类型的指令「{self.name}」的 link 必须以 https:// 开头"
            )
        return self


class Panel(BaseModel):
    """面板配置内容。"""

    items: list[PanelItem] = Field(
        max_length=MAX_ITEMS,
        default_factory=list,
        description=f"面板元素列表（最多 {MAX_ITEMS}）",
    )
    remark: str = Field(
        max_length=REMARK_MAX_LENGTH,
        default="",
        description="开发者备注（不展示给用户）",
    )
    version: int = Field(default=0, description="版本号")


class PanelRecord(BaseModel):
    """面板完整记录（列表/详情接口返回）。"""

    panel_id: str
    scope: Literal["c2c", "group", "channel", "dm"]
    target_type: Literal["all", "specific"]
    panel: Panel
    created_at: str = Field(description="创建时间（RFC3339）")
    updated_at: str = Field(description="更新时间（RFC3339）")
    version: int
    user_openids: list[str] = Field(
        default_factory=list, description="关联用户 openid（c2c+specific）"
    )
    group_openids: list[str] = Field(
        default_factory=list, description="关联群 openid（group+specific）"
    )


class PanelListResponse(BaseModel):
    """面板列表响应。"""

    records: list[PanelRecord] = Field(default_factory=list)
    next_cursor: str = ""
    is_end: bool


class CreatePanelRequest(BaseModel):
    """创建面板请求体。"""

    scope: Literal["c2c", "group", "channel", "dm"]
    panel: Panel
    target_type: Literal["all", "specific"] = "all"
    user_openids: list[str] = Field(default_factory=list)
    group_openids: list[str] = Field(default_factory=list)


class UpdateTargetRequest(BaseModel):
    """增删面板关联对象请求体。"""

    op: Literal["add", "del"]
    user_openids: list[str] = Field(default_factory=list)
    group_openids: list[str] = Field(default_factory=list)


class BotProfile(BaseModel):
    """机器人信息（GET /users/@me）。

    适配器自带的 `User` 模型缺少 share_url / welcome_msg（实测 share_url 有
    真实值），故单独定义。字段全部可选：welcome_msg 实测返回空串，
    union_* 需特殊申请。
    """

    id: str = Field(description="机器人 ID")
    username: str | None = Field(default=None, description="机器人名称")
    avatar: str | None = Field(default=None, description="头像 URL")
    bot: bool | None = Field(default=None, description="是否为机器人")
    share_url: str | None = Field(default=None, description="分享链接")
    welcome_msg: str | None = Field(default=None, description="欢迎语")
    # union_openid / union_user_account 需特殊申请，通常不返回
    union_openid: str | None = None
    union_user_account: str | None = None
