"""日志获取。

模块名用 logger 而非 logging：后者会在包内造成阅读歧义。
"""

from typing import Any

# 不用 logger.opt(colors=True)：消息里含 URL 与尖括号时会被当颜色标签解析
from nonebot.log import logger


def get_logger() -> Any:
    """取 nonebot 的 logger。

    返回类型为 Any：loguru 的 Logger 与 stdlib Logger 接口不同源，
    调用方只依赖两者共有的 info/warning/error。
    """
    return logger
