"""NoneBot 入口文件。

启动 NoneBot 并随之拉起 Maestro WebUI：
bot 通过 WebSocket 连接成功后，WebUI 才会列出该机器人。

WebUI 跑在自己的端口上（MAESTRO_HOST / MAESTRO_PORT，默认 127.0.0.1:8100），
与 NoneBot 的 HOST / PORT 相互独立。

启动: uv run --extra qq python bot.py
访问: http://127.0.0.1:8100
"""

import nonebot
from nonebot.adapters.qq import Adapter as QQAdapter

nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(QQAdapter)

# 启动 WebUI（须在 register_adapter 之后：钩子依赖已注册的适配器）
from maestro.webui import setup as setup_webui

setup_webui()

if __name__ == "__main__":
    nonebot.run()
