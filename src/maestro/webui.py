"""Maestro WebUI - FastAPI 服务端。

前端资源在 `static/`（index.html / app.css / app.js），此模块只负责
REST API、静态资源挂载与随 NoneBot 启动的生命周期。
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from maestro import CreatePanelRequest, Panel, UpdateTargetRequest
from maestro.config import WebUIConfig
from maestro.exceptions import PanelAPIError
from maestro.logger import get_logger
from maestro.registry import BotRegistry

if TYPE_CHECKING:
    from maestro.panel_client import PanelAPIClient

STATIC_DIR = Path(__file__).parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"

# 已连接机器人的客户端注册表
registry = BotRegistry()


def get_client(bot_id: str) -> "PanelAPIClient":
    """按 bot id 取客户端，未注册时返回 404。"""
    client = registry.get(bot_id)
    if client is None:
        raise HTTPException(status_code=404, detail=f"未配置或未连接 bot {bot_id}")
    return client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """独立运行（python -m maestro）时的生命周期：自行初始化 NoneBot。

    随 NoneBot 启动时不会用到此函数——那种模式下 NoneBot 自己管理生命周期，
    客户端由 on_bot_connect 钩子注册。
    """
    import nonebot
    from nonebot.adapters.qq import Adapter as QQAdapter

    # driver 固定为客户端组合：独立模式不需要 ASGI 服务端（跑在自己的
    # uvicorn 上），但适配器 setup() 强制要求 HTTPClientMixin
    nonebot.init(driver="~httpx+~websockets")
    nonebot.get_driver().register_adapter(QQAdapter)

    registry.register_all_from_config()

    # 只用 info/warning：标准 logging 没有 loguru 的 success 级别
    log = get_logger()
    log.info(f"Maestro WebUI 已启动，共 {len(registry)} 个机器人")
    for bot_id in registry.ids():
        log.info(f"  - Bot {bot_id}")

    yield

    registry.clear()


# ==================== FastAPI 应用 ====================

app = FastAPI(
    title="Maestro - QQ 指令面板管理",
    description="NoneBot2 QQ 官方机器人指令面板可视化管理工具",
    version="0.1.0",
    lifespan=lifespan,
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

    async def stop(self, timeout: float = 5) -> None:
        """请求 uvicorn 退出并等待任务收尾。"""
        import uvicorn

        if isinstance(self._server, uvicorn.Server):
            self._server.should_exit = True
        if self._task is not None:
            with suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.wait_for(self._task, timeout=timeout)


def setup() -> None:
    """随 NoneBot 启动 WebUI，并绑定 bot 连接钩子。

    须在 `nonebot.init()` 与 `register_adapter()` 之后调用。
    """
    from nonebot import get_driver
    from nonebot.adapters import Bot as BaseBot

    driver = get_driver()
    host, port = WebUIConfig.bind()
    server = WebUIServer(app, host, port)

    # 钩子参数必须标注为 nonebot.adapters.Bot 及其子类：
    # NoneBot 的 BotParam 按类型解析注入，object 之类的标注会被拒绝
    @driver.on_bot_connect
    async def _on_connect(bot: BaseBot) -> None:
        registry.register_by_id(bot.self_id)

    @driver.on_bot_disconnect
    async def _on_disconnect(bot: BaseBot) -> None:
        registry.remove(bot.self_id)

    @driver.on_startup
    async def _start_webui() -> None:
        await server.start()

    @driver.on_shutdown
    async def _stop_webui() -> None:
        await server.stop()
        registry.clear()
