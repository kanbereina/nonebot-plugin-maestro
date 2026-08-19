"""面板数据模型校验测试。

模型层是提交到 QQ 之前的最后一道拦截：写接口只有 10 QPM，
且超限错误码具误导性，故在本地就挡住非法输入。
"""

import pytest
from pydantic import ValidationError

from nonebot_plugin_maestro.models import (
    Panel,
    PanelItem,
    PanelListResponse,
    CreatePanelRequest,
    UpdateTargetRequest,
)
from nonebot_plugin_maestro.validation import MAX_ITEMS


class TestPanelItem:
    def test_minimal_command(self):
        item = PanelItem(name="权限", desc="查看权限", type="command")
        assert item.only_admin is False  # 默认非管理员限定
        assert item.link is None

    def test_rejects_over_width_name(self):
        with pytest.raises(ValidationError, match="显示宽度"):
            PanelItem(name="一二三四五六七八", desc="描述", type="command")

    def test_rejects_over_width_desc(self):
        # 实测被服务端拒绝的样本
        with pytest.raises(ValidationError, match="显示宽度"):
            PanelItem(
                name="转换",
                desc="解析哔哩哔哩视频，转换为MP3或FLAC格式音频",
                type="command",
            )

    def test_link_type_requires_https(self):
        with pytest.raises(ValidationError, match="https://"):
            PanelItem(name="官网", desc="打开官网", type="link", link="http://x.com")

    def test_link_type_rejects_missing_link(self):
        with pytest.raises(ValidationError, match="https://"):
            PanelItem(name="官网", desc="打开官网", type="link")

    def test_link_type_accepts_https(self):
        item = PanelItem(
            name="官网", desc="打开官网", type="link", link="https://x.com"
        )
        assert item.link == "https://x.com"

    def test_command_type_ignores_link_requirement(self):
        """command 类型不校验 link，允许残留值（提交前由前端清空）。"""
        item = PanelItem(name="权限", desc="查看", type="command", link=None)
        assert item.type == "command"

    def test_rejects_unknown_type(self):
        with pytest.raises(ValidationError):
            PanelItem(name="x", desc="y", type="button")  # type: ignore[arg-type]

    def test_drops_unknown_fields(self):
        """前端内部字段（如 _uid）不应泄漏到提交给 QQ 的数据里。"""
        item = PanelItem.model_validate(
            {"name": "权限", "desc": "查看", "type": "command", "_uid": 7}
        )
        assert "_uid" not in item.model_dump()


class TestPanel:
    def test_defaults_to_empty(self):
        panel = Panel()
        assert panel.items == []
        assert panel.remark == ""

    def test_accepts_max_items(self):
        items = [
            PanelItem(name=f"cmd{i}", desc="d", type="command")
            for i in range(MAX_ITEMS)
        ]
        assert len(Panel(items=items).items) == MAX_ITEMS

    def test_rejects_too_many_items(self):
        items = [
            PanelItem(name=f"cmd{i}", desc="d", type="command")
            for i in range(MAX_ITEMS + 1)
        ]
        with pytest.raises(ValidationError):
            Panel(items=items)

    def test_allows_duplicate_item_names(self):
        """同名指令是合法的——前端曾因用 name 作 key 而少渲染了 chip。"""
        items = [PanelItem(name="测", desc="d", type="command") for _ in range(4)]
        assert len(Panel(items=items).items) == 4


class TestPanelListResponse:
    def test_missing_records_defaults_to_empty(self):
        """空列表时服务端会省略 records 字段，不能因此报错。"""
        resp = PanelListResponse.model_validate({"is_end": True})
        assert resp.records == []
        assert resp.next_cursor == ""


class TestRequests:
    def test_create_defaults_to_global(self):
        req = CreatePanelRequest(scope="group", panel=Panel())
        assert req.target_type == "all"
        assert req.user_openids == []

    def test_create_rejects_bad_scope(self):
        with pytest.raises(ValidationError):
            CreatePanelRequest(scope="guild", panel=Panel())  # type: ignore[arg-type]

    def test_update_target_requires_op(self):
        with pytest.raises(ValidationError):
            UpdateTargetRequest()  # type: ignore[call-arg]

    def test_update_target_rejects_bad_op(self):
        with pytest.raises(ValidationError):
            UpdateTargetRequest(op="remove")  # type: ignore[arg-type]
