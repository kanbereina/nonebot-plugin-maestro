"""Maestro WebUI 启动脚本。

使用方法:
  1. 配置 .env 文件（参考 .env.example）
  2. 运行: uv run python -m maestro

默认监听 http://127.0.0.1:8080
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "maestro.webui:app",
        host="127.0.0.1",
        port=8080,
        reload=True,  # 开发模式自动重载
        log_level="info",
    )
