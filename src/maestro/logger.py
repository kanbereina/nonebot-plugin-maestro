"""日志获取。

模块名用 logger 而非 logging：后者会在包内 `import logging` 时造成歧义
（虽然 Python 3 默认绝对导入不会真的冲突，但阅读时容易误判）。
"""

from typing import Any


def get_logger() -> Any:
    """取 nonebot 的 logger，未安装 nonebot 时回退到标准 logging。

    webui 在核心安装（无 qq extra）下也要能导入，故不在顶层 import nonebot。
    返回类型为 Any：loguru 的 Logger 与 stdlib Logger 接口不同源，
    此处只约定使用两者共有的 info/warning/error。
    """
    try:
        # 不用 logger.opt(colors=True)：消息里含 URL 与尖括号时会被当颜色标签解析
        from nonebot.log import logger
    except ImportError:
        import logging

        return logging.getLogger("maestro")
    else:
        return logger
