"""Maestro WebUI 独立启动脚本（不依赖 bot 连接，纯 REST 管理）。

使用方法:
  1. 配置 .env 文件（参考 .env.example）
  2. 运行: uv run --extra qq python -m maestro

监听地址由 MAESTRO_HOST / MAESTRO_PORT 决定（默认 127.0.0.1:8100），
`.env` 与环境变量均可设置，与 `python bot.py` 共用同一套配置。

若希望 WebUI 跟随 NoneBot 启动（bot 连接后才列出机器人），改用 `python bot.py`。
"""

import uvicorn

from maestro.config import WebUIConfig

if __name__ == "__main__":
    # 先 init 一次以加载 .env，使 WebUIConfig 能读到其中的 MAESTRO_* 配置。
    # app 的 lifespan 之后还会 init（实测 NoneBot 幂等，不覆盖已有 driver）。
    import nonebot

    nonebot.init()

    host, port = WebUIConfig.bind()
    uvicorn.run(
        "maestro.webui:app",
        host=host,
        port=port,
        reload=True,  # 开发模式自动重载
        log_level="info",
    )
