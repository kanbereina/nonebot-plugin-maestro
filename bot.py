"""NoneBot 入口文件。

启动机器人并加载适配器，但不注册任何事件处理器——Maestro 是纯管理工具，
不处理用户消息，只需 Bot 实例用于调用面板 API。
"""

import nonebot
from nonebot.adapters.qq import Adapter as QQAdapter

# 初始化 NoneBot
nonebot.init()

# 注册 QQ 适配器
driver = nonebot.get_driver()
driver.register_adapter(QQAdapter)

if __name__ == "__main__":
    nonebot.run()
