"""本地开发用的 NoneBot 入口。

发布后的用户不需要此文件——插件由宿主 bot 通过 `nb plugin install` 或
`nonebot.load_plugin("nonebot_plugin_maestro")` 加载。此处仅供本仓库调试。

启动: uv run python bot.py
访问: http://127.0.0.1:8100（端口见 MAESTRO_PORT）
"""

import nonebot
from nonebot.adapters.qq import Adapter as QQAdapter

nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(QQAdapter)

# 插件在导入时绑定生命周期钩子，故须在 register_adapter 之后加载
nonebot.load_plugin("nonebot_plugin_maestro")

if __name__ == "__main__":
    nonebot.run()
