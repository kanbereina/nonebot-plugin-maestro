"""显示宽度校验测试。

QQ 服务端按显示宽度而非 len() 统计 name/desc，这里锁定该口径——
它曾导致误判：超宽 desc 被服务端以 code=30013「超出数量限制」拒绝，
而该错误码字面指向数量问题。
"""

import pytest

from nonebot_plugin_maestro.validation import (
    DESC_MAX_WIDTH,
    NAME_MAX_WIDTH,
    check_width,
    display_width,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", 0),
        ("abc", 3),
        ("panel", 5),
        # 中文计 2
        ("权限", 4),
        ("查看用户使用机器人的权限", 24),
        # 全角标点同样计 2
        ("，", 2),
        # 混排：ASCII 计 1，非 ASCII 计 2
        ("转换MP3", 7),
        # emoji 是单个码点，计 2（按 Python 字符迭代，非 UTF-16 码元）
        ("🎼", 2),
    ],
)
def test_display_width(text: str, expected: int):
    assert display_width(text) == expected


def test_display_width_differs_from_len():
    """实测被服务端拒绝的样本：len 未超限但显示宽度超限。

    这是引入 display_width 的直接原因——浏览器 maxlength 与 len()
    都会放过这个串。
    """
    desc = "解析哔哩哔哩视频，转换为MP3或FLAC格式音频"
    assert len(desc) < DESC_MAX_WIDTH  # len 看似合规
    assert display_width(desc) > DESC_MAX_WIDTH  # 实际超限


def test_check_width_passes_at_limit():
    """恰好等于上限应通过（边界不应误杀）。"""
    text = "a" * NAME_MAX_WIDTH
    assert display_width(text) == NAME_MAX_WIDTH
    check_width(text, NAME_MAX_WIDTH, "指令名称")  # 不抛异常


def test_check_width_rejects_over_limit():
    text = "a" * (NAME_MAX_WIDTH + 1)
    with pytest.raises(ValueError, match="显示宽度"):
        check_width(text, NAME_MAX_WIDTH, "指令名称")


def test_check_width_message_contains_context():
    """错误信息需带字段名、实际宽度与字符数，便于定位。"""
    with pytest.raises(ValueError, match="指令名称") as exc:
        check_width("一二三四五六七八", NAME_MAX_WIDTH, "指令名称")
    msg = str(exc.value)
    assert "指令名称" in msg
    assert "16" in msg  # 实际宽度
    assert str(NAME_MAX_WIDTH) in msg  # 上限
