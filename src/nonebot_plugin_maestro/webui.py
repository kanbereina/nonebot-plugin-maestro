"""Maestro WebUI - FastAPI 服务端。

前端资源在 `static/`（index.html / app.css / app.js），此模块只负责
REST API、静态资源挂载与随 NoneBot 启动的生命周期。
"""

import asyncio
from typing import TYPE_CHECKING, Literal
from pathlib import Path
from contextlib import suppress

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from nonebot_plugin_maestro.logger import get_logger
from nonebot_plugin_maestro.models import (
    Panel,
    CreatePanelRequest,
    UpdateTargetRequest,
)
from nonebot_plugin_maestro.registry import BotRegistry
from nonebot_plugin_maestro.exceptions import PanelAPIError

if TYPE_CHECKING:
    from nonebot_plugin_maestro.panel_client import PanelAPIClient

STATIC_DIR = Path(__file__).parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"

# 关停 uvicorn 时等待任务收尾的秒数
SHUTDOWN_TIMEOUT = 5.0

# 已连接机器人的客户端注册表
registry = BotRegistry()


def get_client(bot_id: str) -> "PanelAPIClient":
    """按 bot id 取客户端，未注册时返回 404。"""
    client = registry.get(bot_id)
    if client is None:
        raise HTTPException(status_code=404, detail=f"未配置或未连接 bot {bot_id}")
    return client


# ==================== FastAPI 应用 ====================

# 不设 lifespan：插件由宿主 bot 加载，生命周期由 NoneBot 的钩子驱动
app = FastAPI(
    title="Maestro - QQ 指令面板管理",
    description="NoneBot2 QQ 官方机器人指令面板可视化管理工具",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(PanelAPIError)
async def panel_api_error_handler(request: Request, exc: PanelAPIError) -> JSONResponse:
    """把 QQ 侧业务错误转成 4xx，带上原始 message 与 code。

    这类错误（数量超限、面板不存在、场景不支持）源于输入或账号状态，
    以 500 + traceback 返回会让前端只能显示「Internal Server Error」。
    """
    return JSONResponse(
        status_code=exc.status_code if 400 <= exc.status_code < 500 else 400,
        content={
            "detail": exc.describe(),
            "code": exc.code,
            "trace_id": exc.trace_id,
        },
    )


# ==================== API 路由 ====================


@app.get("/api/bots")
async def list_bots():
    """列出已注册机器人的信息（并发拉取 /users/@me）。

    注意 `/users/@me` 返回的 `id` 是**用户 ID**，与配置里的 appId 不同，
    后者才是本服务的路由键——故额外返回 `bot_id` 供前端拼 URL。
    """

    async def profile(bot_id: str, client: "PanelAPIClient") -> dict[str, object]:
        try:
            me = await client.get_me()
            return {**me.model_dump(mode="json"), "bot_id": bot_id}
        except PanelAPIError as e:
            # 单个机器人凭证失效不该让整页打不开
            return {
                "bot_id": bot_id,
                "id": bot_id,
                "username": None,
                "error": e.describe(),
            }

    results = await asyncio.gather(
        *(profile(bot_id, c) for bot_id, c in registry.items())
    )
    return {"bots": list(results)}


@app.get("/api/bots/{bot_id}/panels")
async def list_panels(
    bot_id: str,
    scope: Literal["c2c", "group", "channel", "dm"],
    cursor: str = "",
    limit: int = 20,
):
    """查询指令面板列表。"""
    client = get_client(bot_id)
    result = await client.list_panels(scope, cursor=cursor, limit=limit)
    return result.model_dump(mode="json")


@app.post("/api/bots/{bot_id}/panels")
async def create_panel(bot_id: str, req: CreatePanelRequest):
    """创建指令面板。"""
    client = get_client(bot_id)
    panel_id = await client.create_panel(
        req.scope,
        req.panel,
        target_type=req.target_type,
        user_openids=req.user_openids,
        group_openids=req.group_openids,
    )
    return {"panel_id": panel_id}


@app.get("/api/bots/{bot_id}/panels/{panel_id}")
async def get_panel(bot_id: str, panel_id: str):
    """查询指令面板详情。"""
    client = get_client(bot_id)
    record = await client.get_panel(panel_id)
    return record.model_dump(mode="json")


@app.put("/api/bots/{bot_id}/panels/{panel_id}")
async def update_panel(bot_id: str, panel_id: str, panel: Panel):
    """修改指令面板内容。"""
    client = get_client(bot_id)
    version = await client.update_panel(panel_id, panel)
    return {"version": version}


@app.delete("/api/bots/{bot_id}/panels/{panel_id}")
async def delete_panel(bot_id: str, panel_id: str):
    """删除指令面板（不可逆操作）。"""
    client = get_client(bot_id)
    await client.delete_panel(panel_id)
    return {"message": "删除成功"}


@app.put("/api/bots/{bot_id}/panels/{panel_id}/target")
async def update_panel_target(bot_id: str, panel_id: str, req: UpdateTargetRequest):
    """增删面板关联对象。"""
    client = get_client(bot_id)
    await client.update_panel_target(
        panel_id,
        req.op,
        user_openids=req.user_openids,
        group_openids=req.group_openids,
    )
    return {"message": f"操作 {req.op} 成功"}


# ==================== 前端界面 ====================


@app.get("/")
async def index() -> FileResponse:
    """返回前端单页应用（static/index.html）。"""
    return FileResponse(INDEX_FILE, media_type="text/html")


# ==================== 随 NoneBot 启动 ====================


class WebUIServer:
    """在 NoneBot 生命周期内托管一个独立的 uvicorn 实例。

    WebUI 不挂载到 NoneBot 的 ASGI app，而是自己监听
    MAESTRO_HOST:MAESTRO_PORT，与 NoneBot 的 HOST/PORT 相互独立——
    因此不要求 driver 提供 ASGI 服务端，`~httpx+~websockets` 即可。
    """

    def __init__(self, asgi_app: FastAPI, host: str, port: int) -> None:
        self._app = asgi_app
        self._host = host
        self._port = port
        self._server: object | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """在当前事件循环中以后台任务启动，不阻塞 bot 连接。"""
        import uvicorn

        # lifespan=off：客户端由 on_bot_connect 钩子注册，
        # 不能再走 app 自带的 lifespan（那会重复 nonebot.init）
        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="warning",
            lifespan="off",
        )
        server = uvicorn.Server(config)
        self._server = server
        self._task = asyncio.create_task(server.serve())
        get_logger().info(f"Maestro WebUI 已启动: http://{self._host}:{self._port}")

    async def stop(self) -> None:
        """请求 uvicorn 退出并等待任务收尾。

        超时用模块常量而非入参：关停时限属实现细节，不应外推给调用方
        （也是 ruff ASYNC109 的意图）。
        """
        import uvicorn

        if isinstance(self._server, uvicorn.Server):
            self._server.should_exit = True
        if self._task is not None:
            with suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.wait_for(self._task, timeout=SHUTDOWN_TIMEOUT)


# 生命周期钩子的绑定见 __init__._setup()：
# 插件加载即注册，无需调用方手动 setup。
