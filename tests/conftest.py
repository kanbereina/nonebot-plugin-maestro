"""pytest 共享配置。

不加载插件本体：`nonebot_plugin_maestro/__init__.py` 在导入时会绑定
生命周期钩子并尝试启动 uvicorn，测试只需要各模块的纯逻辑。
路由测试直接用 FastAPI 的 TestClient，不经 NoneBot。
"""

import os

os.environ["ENVIRONMENT"] = "test"
