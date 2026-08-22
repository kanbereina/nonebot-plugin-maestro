"""面板字段校验。

QQ 服务端按**显示宽度**统计 name/desc 长度（非 ASCII 字符算 2），而不是
Python 的 len() 或浏览器 maxlength 的 UTF-16 码元数。超限时返回
code=30013「超出数量限制」——该错误码同时被复用于数量超限，极易误判。

实测（2026-08-19，生产环境 api.bot.qq.com）：
desc="解析哔哩哔哩视频，转换为MP3或FLAC格式音频" 被拒。
该串 len()=21 < 30，但显示宽度 = 16×2 + 3 + 4 + 2×2 = 43 > 30。
同时验证 4 个 items 可正常保存，确认与数量无关。
"""

# 显示宽度上限（非字符数）
NAME_MAX_WIDTH = 14
DESC_MAX_WIDTH = 30
REMARK_MAX_LENGTH = 255
MAX_ITEMS = 20
# 单次请求允许携带的 openid 数上限（QQ 服务端限制，见 docs/panel-api.md）
MAX_OPENIDS_PER_REQUEST = 20


def display_width(text: str) -> int:
    """按 QQ 服务端口径计算显示宽度：非 ASCII 字符计 2，ASCII 计 1。"""
    return sum(1 if ord(ch) < 128 else 2 for ch in text)


def check_width(text: str, limit: int, field: str) -> None:
    """校验显示宽度，超限时抛出 ValueError（供 pydantic 转成校验错误）。"""
    width = display_width(text)
    if width > limit:
        raise ValueError(
            f"{field}「{text}」显示宽度 {width} 超过上限 {limit}"
            f"（中文与全角标点各计 2，当前 {len(text)} 个字符）"
        )
