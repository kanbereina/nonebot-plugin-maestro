"""Maestro WebUI - FastAPI 服务端。

提供面板管理的 REST API 和前端界面。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from maestro import (
    CreatePanelRequest,
    Panel,
    PanelAPIClient,
    UpdateTargetRequest,
)
from maestro.exceptions import PanelAPIError

STATIC_DIR = Path(__file__).parent / "static"

# ==================== 全局状态管理 ====================

# bot id -> client，按 QQ_BOTS 顺序建立
_clients: dict[str, PanelAPIClient] = {}


def get_client(bot_id: str) -> PanelAPIClient:
    """按 bot id 取客户端。"""
    client = _clients.get(bot_id)
    if client is None:
        raise HTTPException(status_code=404, detail=f"未配置 bot {bot_id}")
    return client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI 生命周期管理：启动时初始化 NoneBot 与各机器人客户端。"""
    # 需要 qq extra：uv sync --extra qq
    import nonebot
    from nonebot.adapters.qq import Adapter as QQAdapter

    # 只初始化配置与适配器，不启动 NoneBot 驱动——服务跑在自己的 uvicorn 上。
    # 适配器的 startup（建 WS / 挂 webhook 路由）不会触发，面板管理是纯 REST，
    # 只用到 adapter.request 发请求。
    #
    # driver 在此固定，不读 .env 的 DRIVER：适配器 setup() 强制要求
    # HTTPClientMixin，而 NoneBot 默认的 ~fastapi 不提供，会直接抛错。
    nonebot.init(driver="~httpx+~websockets")
    nonebot.get_driver().register_adapter(QQAdapter)

    for client in PanelAPIClient.all_from_config():
        _clients[client.bot.self_id] = client

    api_base = next(iter(_clients.values())).base_url
    print(f"✓ Maestro WebUI 已启动，共 {len(_clients)} 个机器人")
    for bot_id in _clients:
        print(f"  - {bot_id}")
    print(f"  API Base: {api_base}")

    yield

    # 关闭时清理
    _clients.clear()


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
    """列出所有已配置机器人的信息（并发拉取 /users/@me）。

    注意 `/users/@me` 返回的 `id` 是**用户 ID**，与配置里的 appId 不同，
    后者才是本服务的路由键——故额外返回 `bot_id` 供前端拼 URL。
    """
    import asyncio

    async def profile(bot_id: str, client: PanelAPIClient) -> dict[str, object]:
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
        *(profile(bot_id, c) for bot_id, c in _clients.items())
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


@app.get("/", response_class=HTMLResponse)
async def index():
    """前端单页应用。"""
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Maestro - QQ 指令面板管理</title>
    <link rel="icon" href="/static/logo.svg">
    <script src="https://cdn.tailwindcss.com"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <style>
      /* 取自 QQ 开放平台的卡片样式约定：ink 墨色分级 + accent 强调色。
         ink-3/ink-4 用 rgba(60,60,67,*) 是 Apple label color 的惯例，
         官方 role-member 背景 rgba(60,60,67,.08) 即出自同一套。 */
      /* QQ 官方设计 token（截取本项目用到的部分，命名与官方一致） */
      :root {
        --bg: #f5f5f7;
        --bg-elev: #ffffff;
        --ink: #1d1d1f;
        --ink-2: #3c3c43;
        --ink-3: #6e6e73;
        --ink-4: #8e8e93;
        --line: rgba(60, 60, 67, .12);
        --line-strong: rgba(60, 60, 67, .22);
        --accent: #0099FF;
        --accent-soft: rgba(0, 153, 255, .08);
        --accent-softer: rgba(0, 153, 255, .16);
        --accent-border: rgba(0, 153, 255, .18);
        --accent-border-strong: rgba(0, 153, 255, .28);
        --danger: #ff3b30;
        --ok: #30d158;
        --online: #34c759;
        --feedback_error: #F74C30;
        --feedback_success: #15D173;
        --fill_standard_primary: rgba(13, 16, 49, 0.04);
        --overlay_light: rgba(0, 77, 255, 0.06);
        --radius-sm: 8px;
        --radius: 14px;
        --radius-lg: 20px;
        --shadow-sm: 0 1px 2px rgba(0,0,0,.04), 0 1px 3px rgba(0,0,0,.06);
        --shadow: 0 4px 16px rgba(17,24,39,.06), 0 1px 4px rgba(17,24,39,.04);
        --shadow-lg: 0 20px 50px rgba(17,24,39,.12), 0 4px 16px rgba(17,24,39,.06);
        --font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC",
                     "Helvetica Neue", system-ui, sans-serif;
        --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      }
      body {
        color: var(--ink); font-family: var(--font-sans); font-size: 14px;
        -webkit-font-smoothing: antialiased; letter-spacing: -.003em;
      }
      .font-mono, code, kbd { font-family: var(--font-mono); }
      /* 截断链：flex 子项必须 min-width:0 才能真正 ellipsis，
         这是官方每个类都带 min-width:0 的原因，缺一层就失效。 */
      .bot-name-row { display: flex; align-items: center; gap: 8px; min-width: 0; }
      .bot-name-row .bot-name {
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        min-width: 0; color: var(--ink); font-weight: 600;
      }
      .bot-role-tag {
        display: inline-flex; align-items: center; gap: 3px; flex-shrink: 0;
        height: 20px; padding: 0 8px; border-radius: 999px;
        font-size: 11px; font-weight: 600; line-height: 1;
      }
      .bot-role-tag.role-admin { color: var(--accent); background: var(--accent-soft); }
      .bot-role-tag.role-member { color: var(--ink-3); background: rgba(60, 60, 67, 0.08); }
      .role-icon { flex-shrink: 0; width: 12px; height: 12px; display: inline-flex; }
      .role-icon svg { width: 100%; height: 100%; display: block; }
      .role-text { flex-shrink: 0; }
      .bot-status-text { flex-shrink: 0; }
      .bot-meta {
        display: flex; align-items: center; gap: 20px; min-width: 0;
        color: var(--ink-3); font-size: 12px;
      }
      .bot-meta-item { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .bot-stats { gap: 16px; }
      .bot-stats .bot-meta-item { display: inline-flex; align-items: center; gap: 4px; }
      .bot-stats .bot-stat-icon { color: var(--ink-4); }
      .bot-stats b { color: var(--ink-2); font-weight: 600; }
      /* 普通白色区块（无渐变、无 hover）：面板列表等内容容器 */
      .surface {
        background: var(--bg-elev); border: 1px solid var(--line);
        border-radius: var(--radius); box-shadow: var(--shadow-sm);
      }
      /* 卡片本体按官方规格：padding 18px、shadow-sm、透明边框（hover 才显色）、
         overflow hidden 裁掉渐变溢出 */
      .bot-card {
        background: #fff;
        background-image: radial-gradient(120% 120% at 100% 0%, rgba(0, 153, 255, .06) 0%, transparent 60%);
        border-radius: var(--radius); padding: 18px;
        box-shadow: var(--shadow-sm);
        border: 1px solid transparent;
        position: relative; overflow: hidden;
        transition: transform .18s, box-shadow .18s, border-color .18s;
      }
      .bot-card.is-clickable:hover {
        border-color: var(--accent-border-strong);
        box-shadow: var(--shadow);
        transform: translateY(-2px);
      }
      /* 开发者备注：带标题的浅色区块，明确标注这是备注。
         min-width 保证极短备注（如「测」）也不会挤成窄条；
         max-width 让长备注仍在容器内换行 */
      .remark {
        display: inline-block; min-width: 300px; max-width: 100%;
        border-radius: var(--radius-sm);
        background: var(--fill_standard_primary);
        border: 1px solid var(--line);
        border-left: 3px solid var(--accent-border-strong);
        padding: 5px 9px;
      }
      .remark-label {
        display: flex; align-items: center; gap: 4px;
        font-size: 10.5px; font-weight: 600; letter-spacing: .02em;
        color: var(--ink-4); margin-bottom: 1px;
      }
      .remark-label-icon { width: 11px; height: 11px; flex-shrink: 0; display: inline-flex; }
      .remark-label-icon svg { width: 100%; height: 100%; display: block; }
      .remark-body {
        font-size: 12.5px; color: var(--ink-2); line-height: 1.45;
        overflow-wrap: anywhere; white-space: pre-wrap;
      }
      /* 区块小标题（如「当前配置指令：」） */
      .field-label {
        font-size: 11px; font-weight: 600; letter-spacing: .02em;
        color: var(--ink-4); margin-bottom: 6px;
      }
      /* 指令预览 chip */
      .cmd-chip {
        display: inline-flex; align-items: center; gap: 5px;
        font-size: 12px; padding: 4px 9px; border-radius: 999px;
        color: var(--ink-2); background: var(--bg-elev);
        border: 1px solid var(--line); max-width: 100%;
      }
      .cmd-chip-icon {
        width: 12px; height: 12px; flex-shrink: 0;
        color: var(--ink-4); display: inline-flex;
      }
      .cmd-chip-icon svg { width: 100%; height: 100%; display: block; }
      .cmd-chip-admin {
        font-size: 10px; font-weight: 600; line-height: 1;
        padding: 2px 4px; border-radius: 4px; flex-shrink: 0;
        color: #0d8a6a; background: rgba(21, 209, 115, .16);
      }
      /* 编辑面板：上下箭头合成一组，共用外框、中间一条分隔线 */
      .move-group {
        display: inline-flex; align-items: stretch; flex-shrink: 0;
        border: 1px solid rgba(60, 60, 67, .25);
        border-radius: var(--radius-sm); overflow: hidden;
      }
      .move-btn {
        display: inline-flex; align-items: center; justify-content: center;
        width: 26px; padding: 3px 0; font-size: 12px; line-height: 1;
        color: var(--ink-3); background: transparent; border: none; cursor: pointer;
        transition: background .15s ease, color .15s ease;
      }
      .move-btn + .move-btn { border-left: 1px solid rgba(60, 60, 67, .25); }
      .move-btn:hover:not(:disabled) { background: rgba(204, 204, 204, .30); color: var(--ink); }
      .move-btn:disabled { opacity: .3; cursor: not-allowed; }
      /* 删除：淡红底 + 红字（官方 button_text_error 的错误色） */
      .btn-danger {
        display: inline-flex; align-items: center; flex-shrink: 0;
        padding: 3px 10px; font-size: 12px; line-height: 1.5;
        border-radius: var(--radius-sm); cursor: pointer;
        color: var(--feedback_error);
        background: rgba(247, 76, 48, .08);
        border: 1px solid rgba(247, 76, 48, .22);
        transition: background .15s ease, border-color .15s ease;
      }
      .btn-danger:hover {
        background: rgba(247, 76, 48, .16);
        border-color: rgba(247, 76, 48, .38);
      }
      /* 仅管理员：淡蓝色开关式按钮，选中后描边与文字转 accent */
      .admin-toggle {
        display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0;
        padding: 6px 12px; font-size: 13px; border-radius: var(--radius-sm);
        cursor: pointer; user-select: none;
        color: var(--ink-3); background: var(--accent-soft);
        border: 1px solid var(--accent-border);
        transition: background .15s ease, color .15s ease, border-color .15s ease;
      }
      .admin-toggle:hover { background: var(--accent-softer); }
      .admin-toggle.is-on {
        color: var(--accent); font-weight: 600;
        background: var(--accent-softer); border-color: var(--accent);
      }
      /* 勾选框保持浏览器默认外观：不设 accent-color，
         避免勾选后填充成深蓝、与淡蓝底冲突 */
      .admin-toggle input { cursor: pointer; }
      /* 「其余 N 个」按钮：灰色按钮样式，点击打开详情 */
      .chip-more-btn {
        display: inline-flex; align-items: center;
        font-size: 12px; padding: 4px 10px; border-radius: 999px;
        color: var(--ink-3); background: var(--fill_standard_primary);
        border: 1px solid var(--line); cursor: pointer; flex-shrink: 0;
        transition: background .15s ease, color .15s ease;
      }
      .chip-more-btn:hover {
        background: rgba(204, 204, 204, .30); color: var(--ink-2);
      }
      /* 次要按钮（官方 button_bg_secondary + button_border_secondary） */
      .btn-ghost {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 7px 14px; font-size: 13px; border-radius: var(--radius-sm);
        color: var(--ink-2); background: transparent;
        border: 1px solid rgba(60, 60, 67, .25); cursor: pointer;
        transition: background .15s ease;
      }
      .btn-ghost:hover { background: rgba(204, 204, 204, .30); }
      /* 数量提示（官方 .limit-hint 规格） */
      .limit-hint {
        display: inline-flex; align-items: center; gap: 6px;
        color: var(--ink-3); font-size: 12.5px; padding: 6px 2px;
      }
      .limit-hint b { color: var(--ink); font-weight: 600; }
      .dot-g {
        width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
        background: var(--ok);
        box-shadow: 0 0 0 3px rgba(52, 199, 89, .15);
      }
      /* 卡片网格：单卡 320–400px，宽屏下多列但不过窄 */
      .bot-grid {
        display: grid; gap: 16px;
        grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
        max-width: 1240px;
      }
      /* 卡片结构（参考官方）：bot-head 基础信息 / 虚线 / bot-foot 标识信息 */
      .bot-head { display: flex; align-items: center; gap: 12px; min-width: 0; }
      .bot-avatar {
        width: 46px; height: 46px; border-radius: 50%; flex-shrink: 0;
        overflow: hidden; display: flex; align-items: center; justify-content: center;
      }
      .bot-avatar img { width: 100%; height: 100%; object-fit: cover; }
      .bot-info { flex: 1; min-width: 0; }
      .bot-action { flex-shrink: 0; width: 16px; height: 16px; color: var(--ink-4); }
      .bot-action svg { width: 100%; height: 100%; display: block; }
      /* 虚线不通到卡片边缘：卡片自带 18px padding，此处仅上移边线 */
      .bot-foot {
        display: flex; align-items: center; justify-content: space-between;
        gap: 12px; min-width: 0; margin-top: 14px; padding-top: 12px;
        border-top: 1px dashed var(--line-strong);
      }
      /* 状态行：圆点 + 文字 + 次级说明 */
      .bot-status { display: flex; align-items: center; gap: 6px; min-width: 0; margin-top: 3px; font-size: 12px; }
      .status-dot {
        width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
        background: var(--online);
      }
      .status-dot.is-bad { background: var(--danger); }
      .bot-status-text { flex-shrink: 0; color: var(--ink-2); font-weight: 500; }
      .bot-stat-icon { width: 13px; height: 13px; display: inline-flex; flex-shrink: 0; }
      .bot-stat-icon svg { width: 100%; height: 100%; display: block; }
      /* ---- 侧边栏（参考 QQ 机器人后台）---- */
      body { background: var(--bg); }
      .layout { display: flex; min-height: 100vh; }
      .sidebar {
        width: 260px; flex-shrink: 0; background: var(--bg-elev);
        border-right: 1px solid var(--line);
        padding: 24px 16px; display: flex; flex-direction: column; gap: 5px;
      }
      .sidebar-brand {
        display: flex; align-items: center; gap: 12px;
        padding: 4px 8px 18px; min-width: 0;
        border-bottom: 1px dashed var(--line-strong);
        margin-bottom: 8px;
      }
      .sidebar-brand-icon {
        flex-shrink: 0; width: 36px; height: 36px;
        border-radius: 9px; object-fit: contain;
      }
      .sidebar-brand-text { min-width: 0; }
      /* 「QQ机器人」加粗，下方「指令面板后台」普通字重、次级墨色 */
      .sidebar-brand-title {
        font-size: 17px; font-weight: 700; color: var(--ink);
        line-height: 1.25; white-space: nowrap;
        overflow: hidden; text-overflow: ellipsis;
      }
      .sidebar-brand-sub {
        font-size: 13px; font-weight: 400; color: var(--ink-3);
        line-height: 1.35; white-space: nowrap;
        overflow: hidden; text-overflow: ellipsis;
      }
      .nav-item {
        display: flex; align-items: center; gap: 10px; min-width: 0;
        padding: 10px 12px; border-radius: 9px; font-size: 14px;
        color: var(--ink-2); cursor: pointer; border: none;
        background: none; width: 100%; text-align: left;
        transition: background .15s ease, color .15s ease;
      }
      .nav-item:hover { background: rgba(60, 60, 67, 0.06); }
      .nav-item.is-active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
      .nav-item-icon { flex-shrink: 0; width: 18px; text-align: center; }
      /* 图标版导航项：未选中时灰显，选中/悬停恢复原色（PNG 只能靠滤镜） */
      .nav-item-logo {
        height: 18px; object-fit: contain; border-radius: 4px;
        filter: grayscale(1); opacity: .45;
        transition: filter .15s ease, opacity .15s ease;
      }
      .nav-item:hover .nav-item-logo,
      .nav-item.is-active .nav-item-logo { filter: none; opacity: 1; }
      .nav-item-label {
        min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      }
      .nav-section {
        font-size: 12px; color: var(--ink-4); font-weight: 600;
        padding: 16px 12px 7px; letter-spacing: .04em;
      }
      /* 场景切换标签（主页面内）。下边框对齐成一条基线，
         选中项用 accent 色下划线，与 QQ 后台的分段导航一致 */
      /* 四个标签宽度有限，桌面端无需滚动；用 flex-wrap 兜住极窄屏，
         避免 overflow-x:auto 在 Windows 上留出滚动条轨道与箭头 */
      .scope-tabs {
        display: flex; gap: 4px; flex-wrap: wrap;
        border-bottom: 1px solid var(--line);
      }
      .scope-tab {
        display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0;
        padding: 9px 14px; font-size: 14px; color: var(--ink-3);
        background: none; border: none; cursor: pointer;
        border-bottom: 2px solid transparent; margin-bottom: -1px;
        transition: color .15s ease, border-color .15s ease;
      }
      .scope-tab:hover { color: var(--ink); }
      .scope-tab.is-active {
        color: var(--accent); font-weight: 600; border-bottom-color: var(--accent);
      }
      .scope-tab-count {
        font-size: 11px; font-weight: 600; line-height: 1;
        padding: 2px 6px; border-radius: 999px;
        background: var(--accent-soft); color: var(--accent);
      }
      /* 场景图标统一灰色（含选中态）——图标只作辨识，不参与状态表达，
         状态由文字颜色与下划线承载。SVG 内部用 currentColor 继承此色。 */
      .scope-tab-icon {
        flex-shrink: 0; width: 17px; height: 17px;
        color: var(--ink-3); display: inline-flex;
        align-items: center; justify-content: center;
      }
      .scope-tab-icon svg { width: 100%; height: 100%; display: block; }
      /* 官方 .content 只有 min-width:0 + min-height:100vh，
         内容不额外向右偏移。大屏下加大留白，避免元素贴边 */
      .content { flex: 1; min-width: 0; min-height: 100vh; padding: 28px 32px; }
      @media (min-width: 1280px) { .content { padding: 36px 56px; } }
      @media (min-width: 1600px) { .content { padding: 40px 72px; } }
      @media (max-width: 820px) {
        .layout { flex-direction: column; }
        .sidebar {
          width: auto; border-right: none;
          border-bottom: 1px solid var(--line);
          flex-direction: row; align-items: center;
          overflow-x: auto; padding: 12px;
        }
        /* 横向排列时改用竖向虚线分隔，横向的边会变成突兀的下划线 */
        .sidebar-brand {
          padding: 0 14px 0 4px; margin-bottom: 0;
          border-bottom: none;
          border-right: 1px dashed var(--line-strong);
        }
        .sidebar-brand-icon { width: 30px; height: 30px; }
        .sidebar-brand-sub { display: none; }
        .nav-section { display: none; }
        .nav-item { width: auto; white-space: nowrap; }
        .content { padding: 20px 16px; }
      }
    </style>
</head>
<body>
    <div x-data="maestroApp()" class="layout">
        <!-- ============ 侧边栏 ============ -->
        <aside class="sidebar">
            <div class="sidebar-brand">
                <img class="sidebar-brand-icon" src="/static/logo.svg" alt="QQ机器人">
                <div class="sidebar-brand-text">
                    <div class="sidebar-brand-title">QQ机器人</div>
                    <div class="sidebar-brand-sub">指令面板后台</div>
                </div>
            </div>

            <div class="nav-section">机器人</div>
            <button class="nav-item" :class="!activeBot ? 'is-active' : ''"
                    @click="backToBots()">
                <img class="nav-item-icon nav-item-logo" src="/static/logo.svg" alt="">
                <span class="nav-item-label">我的机器人</span>
            </button>

            <div class="mt-auto pt-4" style="font-size: 11px; color: var(--ink-4)">
                <div class="nav-item-label">Maestro · 本地管理工具</div>
            </div>
        </aside>

        <!-- ============ 主内容区 ============ -->
        <main class="content">

        <!-- ============ 视图一：机器人卡片 ============ -->
        <div x-show="!activeBot">
            <!-- 标题与数量提示同行，提示靠右（窄屏自动折行） -->
            <div class="mb-6 flex items-center justify-between gap-4 flex-wrap">
                <div>
                    <h1 class="text-2xl font-bold" style="color: var(--ink)">我的机器人</h1>
                    <p class="text-sm mt-1" style="color: var(--ink-3)">
                        管理当前已配置的 QQ 机器人账号
                    </p>
                </div>
                <!-- 加载完成后才显示，避免闪现「0 个」 -->
                <div class="limit-hint" x-show="!botsLoading">
                    <span class="dot-g"></span>
                    <span> 当前已配置的机器人数量：<b x-text="bots.length"></b> 个 </span>
                </div>
            </div>

            <div x-show="botsLoading" class="text-center py-16" style="color: var(--ink-4)">
                正在加载机器人信息...
            </div>

            <!-- 卡片定宽上限，避免宽屏下被拉得过长 -->
            <div x-show="!botsLoading" class="bot-grid">
                <template x-for="bot in bots" :key="bot.bot_id">
                    <div @click="!bot.error && openBot(bot)"
                         class="bot-card"
                         :class="bot.error ? 'opacity-70 cursor-not-allowed' : 'is-clickable cursor-pointer'">
                        <!-- 虚线之上：基础信息（名称、凭证、连通状态） -->
                        <div class="bot-head">
                            <div class="bot-avatar" style="background: rgba(60,60,67,.06)">
                                <img x-show="bot.avatar" :src="bot.avatar"
                                     :alt="bot.username || bot.bot_id" referrerpolicy="no-referrer">
                                <span x-show="!bot.avatar" style="color: var(--ink-4)">🤖</span>
                            </div>

                            <div class="bot-info">
                                <div class="bot-name-row">
                                    <span class="bot-name text-[15px]" x-text="bot.username || '(未命名)'"></span>
                                    <span class="bot-role-tag"
                                          :class="bot.error ? 'role-member' : 'role-admin'">
                                        <span class="role-icon" x-html="icons.shield"></span>
                                        <span class="role-text" x-text="bot.error ? '凭证异常' : '凭证有效'"></span>
                                    </span>
                                </div>
                                <div class="bot-status">
                                    <span class="status-dot" :class="bot.error ? 'is-bad' : ''"></span>
                                    <!-- 按项目约定：API 可访问即视为在线 -->
                                    <span class="bot-status-text" x-text="bot.error ? '离线' : '在线'"></span>
                                </div>
                            </div>

                            <span class="bot-action" x-show="!bot.error" x-html="icons.chevron"></span>
                        </div>

                        <!-- 虚线之下：标识信息（appId） -->
                        <div class="bot-foot">
                            <div class="bot-meta bot-stats">
                                <span class="bot-meta-item" :title="`appId ${bot.bot_id}`">
                                    <span class="bot-stat-icon" x-html="icons.hash"></span>
                                    appId <b x-text="bot.bot_id"></b>
                                </span>
                            </div>
                        </div>

                        <p x-show="bot.error" class="mt-3 text-xs" style="color: var(--feedback_error)"
                           x-text="bot.error"></p>
                    </div>
                </template>
            </div>

            <div x-show="!botsLoading && bots.length === 0"
                 class="text-center py-16" style="color: var(--ink-4)">
                未配置任何机器人，请检查 .env 中的 QQ_BOTS
            </div>
        </div>

        <!-- ============ 视图二：指令面板配置 ============ -->
        <div x-show="activeBot">
            <template x-if="activeBot">
                <!-- 标题与返回按钮同行，返回置于右侧 -->
                <div class="mb-6 flex items-center justify-between gap-4 flex-wrap">
                    <div class="flex items-center gap-3 min-w-0">
                        <img :src="activeBot.avatar" x-show="activeBot.avatar" referrerpolicy="no-referrer"
                             class="w-11 h-11 rounded-full object-cover shrink-0"
                             style="background: rgba(60,60,67,.06)">
                        <div class="min-w-0">
                            <h1 class="text-2xl font-bold truncate" style="color: var(--ink)"
                                x-text="activeBot.username || activeBot.bot_id"></h1>
                            <p class="text-sm mt-0.5" style="color: var(--ink-3)">
                                指令面板配置 ·
                                <span class="font-mono" x-text="`appId ${activeBot.bot_id}`"></span>
                            </p>
                        </div>
                    </div>
                    <button @click="backToBots()" class="btn-ghost shrink-0">
                        <span x-html="icons.back"></span>
                        返回
                    </button>
                </div>
            </template>

            <!-- 场景切换（主页面内，不占用侧边栏）。
                 计数按场景独立缓存，且仅在四个场景都拉完后显示，
                 否则切换瞬间会短暂显示上一个场景的数字 -->
            <div class="scope-tabs mb-5">
                <template x-for="s in scopes" :key="s.value">
                    <button class="scope-tab"
                            :class="scope === s.value ? 'is-active' : ''"
                            @click="switchScope(s.value)">
                        <span class="scope-tab-icon" x-html="icons[s.value]"></span>
                        <span x-text="s.label"></span>
                        <span class="scope-tab-count"
                              x-show="countsReady && scopeCounts[s.value] > 0"
                              x-text="scopeCounts[s.value]"></span>
                    </button>
                </template>
            </div>

            <!-- 面板列表 -->
            <div class="surface p-5 mb-6">
                <div class="flex justify-between items-center mb-1 gap-4">
                    <h2 class="text-lg font-semibold" style="color: var(--ink)">
                        <span x-text="scopes.find(s => s.value === scope)?.label"></span>面板
                    </h2>
                    <button @click="showCreateModal = true"
                            class="px-4 py-2 text-sm text-white rounded-lg shadow-sm transition shrink-0"
                            style="background: var(--accent)">
                        + 新建面板
                    </button>
                </div>
                <p class="text-xs mb-4" style="color: var(--ink-4)" x-text="scopeHint()"></p>

                <div x-show="loading" class="text-center py-10 text-[color:var(--ink-4)]">加载中...</div>

                <!-- 面板卡片 -->
                <div x-show="!loading && panels.length > 0" class="space-y-4">
                    <template x-for="panel in panels" :key="panel.panel_id">
                        <div class="rounded-lg p-4 transition" style="border: 1px solid var(--line)">
                            <div class="flex justify-between items-start mb-3 gap-4">
                                <div class="flex-1 min-w-0">
                                    <div class="flex items-center gap-2 mb-1 flex-wrap">
                                        <span class="font-mono text-sm text-[color:var(--ink-2)]" x-text="panel.panel_id"></span>
                                        <span class="text-xs px-2 py-0.5 bg-slate-100 text-[color:var(--ink-2)] rounded-full"
                                              x-text="panel.target_type === 'all' ? '全局' : '指定对象'"></span>
                                        <span class="text-xs px-2 py-0.5 rounded-full" style="background: var(--accent-soft); color: var(--accent)"
                                              x-text="`v${panel.version}`"></span>
                                    </div>
                                    <p class="text-sm text-[color:var(--ink-3)]">
                                        <span x-text="panel.panel.items.length"></span> 个指令 ·
                                        更新于 <span x-text="new Date(panel.updated_at).toLocaleString('zh-CN')"></span>
                                    </p>
                                    <!-- 开发者备注：带「开发者备注」标题，与元信息区分 -->
                                    <div x-show="panel.panel.remark" class="remark mt-2">
                                        <div class="remark-label">
                                            <span class="remark-label-icon" x-html="icons.note"></span>
                                            开发者备注
                                        </div>
                                        <p class="remark-body" x-text="panel.panel.remark"></p>
                                    </div>
                                </div>
                                <div class="flex gap-2 shrink-0">
                                    <button @click="viewPanel(panel)"
                                            class="px-3 py-1 text-sm bg-slate-50 text-[color:var(--ink-2)] rounded-md hover:bg-slate-100 transition">
                                        查看
                                    </button>
                                    <button @click="startEdit(panel)"
                                            class="px-3 py-1 text-sm rounded-md transition" style="background: var(--accent-soft); color: var(--accent)">
                                        编辑
                                    </button>
                                    <button @click="confirmDelete(panel.panel_id)"
                                            class="px-3 py-1 text-sm bg-red-50 text-red-600 rounded-md hover:bg-red-100 transition">
                                        删除
                                    </button>
                                </div>
                            </div>
                            <!-- 指令预览：超出 6 个以 … 省略 -->
                            <div x-show="panel.panel.items.length > 0">
                                <div class="field-label">当前配置指令：</div>
                                <div class="flex flex-wrap gap-2 items-center">
                                    <!-- key 用索引：指令名允许重复（实测同名会被 Alpine 按 key 去重，
                                         导致 chip 少显示且与计数不符），预览只读故无重排问题 -->
                                    <template x-for="(item, i) in panel.panel.items.slice(0, 6)" :key="i">
                                        <span class="cmd-chip">
                                            <span class="cmd-chip-icon"
                                                  x-html="item.type === 'command' ? icons.slash : icons.link"></span>
                                            <span x-text="item.name"></span>
                                            <span x-show="item.only_admin" class="cmd-chip-admin"
                                                  title="仅管理员可见">管</span>
                                        </span>
                                    </template>
                                    <button x-show="panel.panel.items.length > 6" class="chip-more-btn"
                                            @click.stop="viewPanel(panel)"
                                            :title="panel.panel.items.slice(6).map(i => i.name).join('、')"
                                            x-text="`... 其余 ${panel.panel.items.length - 6} 个`"></button>
                                </div>
                            </div>
                        </div>
                    </template>
                </div>

                <div x-show="!loading && panels.length === 0" class="text-center py-12 text-[color:var(--ink-4)]">
                    当前场景暂无面板，点击右上角「新建面板」开始创建
                </div>
            </div>
        </div>
        </main>

        <!-- 模态框放在 main 之外：position:fixed 覆盖全屏，不受内容列约束 -->

        <!-- 创建面板模态框 -->
        <div x-show="showCreateModal"
             class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
             @click.self="showCreateModal = false">
            <div class="bg-white rounded-lg shadow-xl p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
                <h3 class="text-xl font-semibold mb-4">新建面板</h3>
                <form @submit.prevent="createPanel()">
                    <div class="mb-4">
                        <label class="block text-sm font-medium text-gray-700 mb-1">备注（开发者可见）</label>
                        <input x-model="newPanel.remark" type="text" maxlength="255"
                               class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-[color:var(--accent)] focus:border-[color:var(--accent)]"
                               placeholder="选填，最多 255 字符">
                    </div>
                    <div class="mb-4">
                        <label class="block text-sm font-medium text-gray-700 mb-2">指令项</label>
                        <p class="text-xs text-[color:var(--ink-4)] mb-2">拖动左侧 ⠿ 手柄可调整顺序</p>
                        <div class="space-y-3">
                            <template x-for="(item, index) in newPanel.items" :key="item._uid">
                                <div draggable="true"
                                     @dragstart="onDragStart(index, $event, 'new')"
                                     @dragover.prevent="onDragOver(index)"
                                     @drop.prevent="onDrop(index, 'new')"
                                     @dragend="resetDrag()"
                                     class="border rounded p-3 transition"
                                     :class="[
                                         dragIndex === index ? 'opacity-40' : '',
                                         dragOverIndex === index && dragIndex !== index
                                             ? 'border-2 bg-[color:var(--accent-soft)] border-[color:var(--accent)]'
                                             : 'border-gray-200'
                                     ]">
                                    <div class="flex justify-between items-start mb-2">
                                        <div class="flex items-center gap-2">
                                            <span @mousedown="dragEnabled = true"
                                                  class="cursor-grab active:cursor-grabbing select-none text-[color:var(--ink-4)] hover:text-[color:var(--ink-2)] px-1"
                                                  title="拖动排序">⠿</span>
                                            <span class="text-sm font-medium text-gray-600" x-text="`指令 ${index + 1}`"></span>
                                        </div>
                                        <button type="button" class="btn-danger"
                                                @click="newPanel.items.splice(index, 1)">删除</button>
                                    </div>
                                    <input x-model="item.name" type="text" required
                                           class="w-full px-3 py-2 border border-gray-300 rounded-md mb-1 focus:outline-none focus:ring-[color:var(--accent)] focus:border-[color:var(--accent)]"
                                           :class="width(item.name) > 14 ? 'border-red-400 bg-red-50' : ''"
                                           placeholder="指令名称">
                                    <p class="text-xs mb-2 text-right"
                                       :class="width(item.name) > 14 ? 'text-red-600 font-medium' : 'text-gray-400'"
                                       x-text="`名称宽度 ${width(item.name)}/14`"></p>
                                    <input x-model="item.desc" type="text" required
                                           class="w-full px-3 py-2 border border-gray-300 rounded-md mb-1 focus:outline-none focus:ring-[color:var(--accent)] focus:border-[color:var(--accent)]"
                                           :class="width(item.desc) > 30 ? 'border-red-400 bg-red-50' : ''"
                                           placeholder="指令描述">
                                    <p class="text-xs mb-2 text-right"
                                       :class="width(item.desc) > 30 ? 'text-red-600 font-medium' : 'text-gray-400'"
                                       x-text="`描述宽度 ${width(item.desc)}/30`"></p>
                                    <div class="flex gap-4">
                                        <select x-model="item.type"
                                                class="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-[color:var(--accent)] focus:border-[color:var(--accent)]">
                                            <option value="command">命令</option>
                                            <option value="link">链接</option>
                                        </select>
                                        <input x-show="item.type === 'link'" x-model="item.link" type="url"
                                               class="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-[color:var(--accent)] focus:border-[color:var(--accent)]"
                                               placeholder="https://...">
                                        <label class="admin-toggle"
                                               :class="item.only_admin ? 'is-on' : ''">
                                            <input type="checkbox" x-model="item.only_admin" class="rounded">
                                            <span>仅管理员</span>
                                        </label>
                                    </div>
                                </div>
                            </template>
                        </div>
                        <button type="button" @click="addPanelItem()"
                                :disabled="newPanel.items.length >= 20"
                                class="mt-3 w-full py-2 border-2 border-dashed border-gray-300 rounded-md text-gray-500 hover:border-[color:var(--accent)] hover:text-[color:var(--accent)] transition disabled:opacity-50 disabled:cursor-not-allowed">
                            + 添加指令项（最多 20 个）
                        </button>
                    </div>
                    <div class="flex gap-3 justify-end">
                        <button type="button" @click="showCreateModal = false"
                                class="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 transition">
                            取消
                        </button>
                        <button type="submit" :disabled="newPanel.items.length === 0"
                                class="px-4 py-2 text-white rounded-md transition disabled:opacity-50 disabled:cursor-not-allowed" style="background: var(--accent)">
                            创建
                        </button>
                    </div>
                </form>
            </div>
        </div>

        <!-- 编辑面板模态框 -->
        <div x-show="editingPanel"
             class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
             @click.self="editingPanel = null">
            <div class="bg-white rounded-lg shadow-xl p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
                <template x-if="editingPanel">
                    <form @submit.prevent="saveEdit()">
                        <div class="flex justify-between items-start mb-4">
                            <div>
                                <h3 class="text-xl font-semibold">编辑面板</h3>
                                <p class="text-sm text-gray-500 mt-1">
                                    <span x-text="editingPanel.panel_id"></span> ·
                                    当前 v<span x-text="editingPanel.version"></span>
                                </p>
                            </div>
                            <button type="button" @click="editingPanel = null"
                                    class="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
                        </div>
                        <div class="mb-4">
                            <label class="block text-sm font-medium text-gray-700 mb-1">备注（开发者可见）</label>
                            <input x-model="editForm.remark" type="text" maxlength="255"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-[color:var(--accent)] focus:border-[color:var(--accent)]"
                                   placeholder="仅开发者可见，不展示给用户">
                        </div>
                        <div class="mb-4">
                            <label class="block text-sm font-medium text-gray-700 mb-2">
                                指令项（<span x-text="editForm.items.length"></span>/20）
                            </label>
                            <p class="text-xs text-[color:var(--ink-4)] mb-2">拖动左侧 ⠿ 手柄可调整顺序，顺序即用户看到的展示顺序</p>
                            <div class="space-y-3">
                                <template x-for="(item, index) in editForm.items" :key="item._uid">
                                    <div draggable="true"
                                         @dragstart="onDragStart(index, $event)"
                                         @dragover.prevent="onDragOver(index)"
                                         @drop.prevent="onDrop(index)"
                                         @dragend="resetDrag()"
                                         class="border rounded p-3 transition"
                                         :class="[
                                             dragIndex === index ? 'opacity-40' : '',
                                             dragOverIndex === index && dragIndex !== index
                                                 ? 'border-2 bg-[color:var(--accent-soft)] border-[color:var(--accent)]'
                                                 : 'border-gray-200'
                                         ]">
                                        <div class="flex justify-between items-start mb-2">
                                            <div class="flex items-center gap-2">
                                                <span @mousedown="dragEnabled = true"
                                                      class="cursor-grab active:cursor-grabbing select-none text-[color:var(--ink-4)] hover:text-[color:var(--ink-2)] px-1"
                                                      title="拖动排序">⠿</span>
                                                <span class="text-sm font-medium text-gray-600" x-text="`指令 ${index + 1}`"></span>
                                            </div>
                                            <div class="flex gap-2 items-center">
                                                <div class="move-group">
                                                    <button type="button" class="move-btn"
                                                            @click="moveItem(index, -1)" :disabled="index === 0"
                                                            title="上移">↑</button>
                                                    <button type="button" class="move-btn"
                                                            @click="moveItem(index, 1)"
                                                            :disabled="index === editForm.items.length - 1"
                                                            title="下移">↓</button>
                                                </div>
                                                <button type="button" class="btn-danger"
                                                        @click="editForm.items.splice(index, 1)">删除</button>
                                            </div>
                                        </div>
                                        <div class="flex items-center gap-2 mb-2">
                                            <input x-model="item.name" type="text" required
                                                   class="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-[color:var(--accent)] focus:border-[color:var(--accent)]"
                                                   :class="width(item.name) > 14 ? 'border-red-400 bg-red-50' : ''"
                                                   placeholder="指令名称">
                                            <span class="text-xs w-12 text-right"
                                                  :class="width(item.name) > 14 ? 'text-red-600 font-medium' : 'text-gray-400'"
                                                  x-text="`${width(item.name)}/14`"></span>
                                        </div>
                                        <div class="flex items-center gap-2 mb-2">
                                            <input x-model="item.desc" type="text" required
                                                   class="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-[color:var(--accent)] focus:border-[color:var(--accent)]"
                                                   :class="width(item.desc) > 30 ? 'border-red-400 bg-red-50' : ''"
                                                   placeholder="指令描述">
                                            <span class="text-xs w-12 text-right"
                                                  :class="width(item.desc) > 30 ? 'text-red-600 font-medium' : 'text-gray-400'"
                                                  x-text="`${width(item.desc)}/30`"></span>
                                        </div>
                                        <div class="flex gap-4">
                                            <select x-model="item.type"
                                                    class="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-[color:var(--accent)] focus:border-[color:var(--accent)]">
                                                <option value="command">命令</option>
                                                <option value="link">链接</option>
                                            </select>
                                            <input x-show="item.type === 'link'" x-model="item.link" type="url"
                                                   class="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-[color:var(--accent)] focus:border-[color:var(--accent)]"
                                                   placeholder="https://...">
                                            <label class="admin-toggle"
                                                   :class="item.only_admin ? 'is-on' : ''">
                                                <input type="checkbox" x-model="item.only_admin" class="rounded">
                                                <span>仅管理员</span>
                                            </label>
                                        </div>
                                    </div>
                                </template>
                            </div>
                            <button type="button" @click="addEditItem()"
                                    :disabled="editForm.items.length >= 20"
                                    class="mt-3 w-full py-2 border-2 border-dashed border-gray-300 rounded-md text-gray-500 hover:border-[color:var(--accent)] hover:text-[color:var(--accent)] transition disabled:opacity-50 disabled:cursor-not-allowed">
                                + 添加指令项（最多 20 个）
                            </button>
                        </div>
                        <div class="flex gap-3 justify-end">
                            <button type="button" @click="editingPanel = null"
                                    class="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 transition">
                                取消
                            </button>
                            <button type="submit" :disabled="editForm.items.length === 0 || saving"
                                    class="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition disabled:opacity-50 disabled:cursor-not-allowed">
                                <span x-text="saving ? '保存中...' : '保存'"></span>
                            </button>
                        </div>
                    </form>
                </template>
            </div>
        </div>

        <!-- 查看面板模态框 -->
        <div x-show="viewingPanel"
             class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
             @click.self="viewingPanel = null">
            <div class="bg-white rounded-lg shadow-xl p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
                <template x-if="viewingPanel">
                    <div>
                        <div class="flex justify-between items-start mb-4">
                            <div>
                                <h3 class="text-xl font-semibold" x-text="viewingPanel.panel_id"></h3>
                                <p class="text-sm text-gray-500 mt-1">
                                    版本: v<span x-text="viewingPanel.version"></span> |
                                    创建: <span x-text="new Date(viewingPanel.created_at).toLocaleString('zh-CN')"></span>
                                </p>
                            </div>
                            <button @click="viewingPanel = null" class="text-gray-400 hover:text-gray-600 text-2xl">&times;</button>
                        </div>
                        <div x-show="viewingPanel.panel.remark" class="remark mb-4">
                            <div class="remark-label">
                                <span class="remark-label-icon" x-html="icons.note"></span>
                                开发者备注
                            </div>
                            <p class="remark-body" x-text="viewingPanel.panel.remark"></p>
                        </div>
                        <div class="field-label">当前配置指令：</div>
                        <div class="space-y-3">
                            <!-- 同上：指令名可能重复，key 用索引避免被去重 -->
                            <template x-for="(item, i) in viewingPanel.panel.items" :key="i">
                                <div class="border border-gray-200 rounded p-3">
                                    <div class="flex items-start justify-between mb-1">
                                        <div class="flex items-center gap-2">
                                            <span class="cmd-chip-icon"
                                                  x-html="item.type === 'command' ? icons.slash : icons.link"></span>
                                            <span class="font-medium" x-text="item.name"></span>
                                            <span x-show="item.only_admin" class="cmd-chip-admin">仅管理员</span>
                                        </div>
                                    </div>
                                    <p class="text-sm text-gray-600" x-text="item.desc"></p>
                                    <p x-show="item.link" class="text-sm mt-1"
                                       style="color: var(--accent)" x-text="item.link"></p>
                                </div>
                            </template>
                        </div>
                    </div>
                </template>
            </div>
        </div>
    </div>

    <script>
        function maestroApp() {
            return {
                bots: [],
                botsLoading: false,
                activeBot: null,
                scope: 'group',
                scopes: [
                    { value: 'group',   label: '群聊' },
                    { value: 'c2c',     label: '私聊' },
                    { value: 'channel', label: '频道' },
                    { value: 'dm',      label: '频道私信' }
                ],
                // 场景图标（内联 SVG，fill/stroke 用 currentColor 继承 .scope-tab-icon 的灰色）
                icons: {
                    // 私聊：单用户
                    c2c: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
                               stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="8" r="3.6"/>
                        <path d="M4.5 20.5c0-3.6 3.4-6 7.5-6s7.5 2.4 7.5 6"/>
                    </svg>`,
                    // 群聊：多用户
                    group: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
                                 stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="9" cy="8" r="3.2"/>
                        <path d="M2.5 20c0-3.3 2.9-5.5 6.5-5.5s6.5 2.2 6.5 5.5"/>
                        <path d="M16.5 5.2a3.2 3.2 0 0 1 0 6"/>
                        <path d="M18 14.9c2.2.6 3.5 2.2 3.5 4.4"/>
                    </svg>`,
                    // 频道：官方 guild.svg 的图形部分（原图 viewBox 98x26，
                    // 右侧是文字，此处裁到 0 0 26 26 只取徽标）
                    channel: `<svg viewBox="0 0 26 26" fill="none">
                        <path d="M20.9003 8.98713H17.9705L18.2468 7.15772C18.2615 7.05993 18.1851 6.97363 18.0851 6.97363H16.1986C16.1163 6.97363 16.0487 7.03116 16.0369 7.1117L15.7519 8.98713H10.8327L11.1089 7.15772C11.1236 7.05993 11.0472 6.97363 10.9473 6.97363H9.06361C8.98133 6.97363 8.91375 7.03116 8.90199 7.1117L8.61695 8.98713H5.64014C5.55786 8.98713 5.49027 9.04466 5.47851 9.1252L5.22285 10.8165C5.20816 10.9143 5.28456 11.0006 5.38448 11.0006H8.31133L7.96164 13.3046C7.01247 13.1263 6.03391 13.0228 5.03184 13.0141C4.94956 13.0141 4.87904 13.0745 4.86728 13.1522L4.61162 14.8435C4.59693 14.9385 4.67627 15.0247 4.77325 15.0247C6.03685 15.0334 6.88904 15.1369 7.65896 15.2951L7.11826 18.8648C7.10356 18.9626 7.17997 19.0489 7.27988 19.0489H9.16353C9.24581 19.0489 9.3134 18.9913 9.32515 18.9108L9.78651 15.8762C11.6819 16.5608 13.3892 17.6308 14.8027 18.9885C15.4022 19.5637 16.416 19.2214 16.5394 18.4103L16.6129 17.9242L16.7481 17.0354H19.7249C19.8072 17.0354 19.8748 16.9778 19.8865 16.8973L20.1422 15.206C20.1569 15.1082 20.0805 15.0219 19.9805 15.0219H17.0507L17.662 10.9978H20.6388C20.7211 10.9978 20.7887 10.9402 20.8004 10.8597L21.0561 9.16834C21.0708 9.07055 20.9944 8.98425 20.8944 8.98425L20.9003 8.98713ZM15.3904 11.3746L14.7351 15.6863C14.6969 15.9308 14.4119 16.043 14.2062 15.9021C13.0278 15.088 11.7319 14.4264 10.3507 13.9432C10.2009 13.8914 10.1098 13.7447 10.1333 13.5894L10.483 11.2796C10.5065 11.1186 10.6475 11.0006 10.815 11.0006H15.0584C15.2641 11.0006 15.4198 11.179 15.3904 11.3774V11.3746Z" fill="currentColor"/>
                        <path d="M0.240966 16.5783C0.649432 18.773 1.53101 19.9466 2.70646 20.9016C3.91129 21.8335 5.38941 22.5325 8.16051 22.8547C9.4153 23.0014 10.9434 23.0445 12.6742 23.0445C14.4051 23.0445 15.9331 23.0014 17.1879 22.8547C19.9561 22.5296 21.4371 21.8307 22.642 20.9016C23.8145 19.9466 24.699 18.773 25.1075 16.5783C25.2926 15.5831 25.3484 14.3721 25.3484 13C25.3484 11.628 25.2926 10.4141 25.1075 9.42177C24.699 7.22706 23.8174 6.05348 22.642 5.0985C21.4371 4.16654 19.959 3.46757 17.1879 3.14541C15.9331 2.99871 14.4051 2.95557 12.6742 2.95557C10.9434 2.95557 9.4153 2.99871 8.16051 3.14541C5.39234 3.47045 3.91129 4.16942 2.70646 5.0985C1.53101 6.0506 0.649432 7.22418 0.240966 9.41889C0.0558335 10.4141 0 11.6251 0 12.9972C0 14.3692 0.0558335 15.5831 0.240966 16.5754V16.5783ZM2.11286 9.75256C2.43023 8.04684 3.03264 7.25582 3.90247 6.54247C4.72528 5.90965 5.84489 5.28835 8.38385 4.9892C9.42118 4.86839 10.7847 4.81086 12.6713 4.81086C14.5579 4.81086 15.9214 4.86839 16.9587 4.9892C19.4977 5.28547 20.6173 5.90965 21.4401 6.54247C22.3099 7.25582 22.9123 8.04684 23.2297 9.75256C23.3737 10.5234 23.4413 11.5532 23.4413 12.9972C23.4413 14.4411 23.3737 15.4709 23.2297 16.2418C22.9123 17.9475 22.3099 18.7385 21.4401 19.4519C20.6173 20.0847 19.4977 20.706 16.9587 21.0051C15.9214 21.1259 14.5579 21.1835 12.6713 21.1835C10.7847 21.1835 9.42118 21.1259 8.38385 21.0051C5.84489 20.7089 4.72528 20.0847 3.90247 19.4519C3.03264 18.7385 2.43023 17.9475 2.11286 16.2418C1.96887 15.4709 1.90128 14.4411 1.90128 12.9972C1.90128 11.5532 1.96887 10.5234 2.11286 9.75256Z" fill="currentColor"/>
                    </svg>`,
                    // 频道私信：邮件
                    dm: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
                              stroke-linecap="round" stroke-linejoin="round">
                        <rect x="2.5" y="5" width="19" height="14" rx="2.5"/>
                        <path d="M3.5 7.5l7.3 5.2a2 2 0 0 0 2.4 0l7.3-5.2"/>
                    </svg>`,
                    // 盾牌对勾（官方 role-tag 用的同一枚）
                    shield: `<svg viewBox="0 0 18 21" fill="none" xmlns="http://www.w3.org/2000/svg"
                                  width="100%" height="100%">
                        <path d="M5.45107 8.58206C5.11913 8.25012 4.58094 8.25012 4.24899 8.58206C3.91704 8.91401 3.91704 9.4522 4.24899 9.78415L6.54188 12.077C7.26435 12.7995 8.43571 12.7995 9.15818 12.077L13.4511 7.78415C13.783 7.4522 13.783 6.91401 13.4511 6.58207C13.1191 6.25012 12.5809 6.25012 12.249 6.58207L7.9561 10.875C7.89752 10.9335 7.80254 10.9335 7.74396 10.875L5.45107 8.58206Z" fill="currentColor"/>
                        <path fill-rule="evenodd" clip-rule="evenodd" d="M10.1475 0.198012C9.30264 -0.0660042 8.39736 -0.0660039 7.5525 0.198012L3.0525 1.60426C1.23649 2.17177 0 3.85363 0 5.75625V12.6258C0 13.1357 0.129965 13.6373 0.377626 14.0831C1.91478 16.8499 4.399 18.969 7.37363 20.0507L7.75887 20.1908C8.46371 20.4471 9.23629 20.4471 9.94113 20.1908L10.3264 20.0507C13.301 18.969 15.7852 16.8499 17.3224 14.0831C17.57 13.6373 17.7 13.1357 17.7 12.6258V5.75625C17.7 3.85363 16.4635 2.17177 14.6475 1.60426L10.1475 0.198012ZM8.05957 1.82063C8.57425 1.65979 9.12575 1.65979 9.64043 1.82063L14.1404 3.22688C15.2467 3.5726 16 4.59718 16 5.75625V12.6258C16 12.8468 15.9437 13.0642 15.8363 13.2575C14.498 15.6664 12.3352 17.5113 9.74541 18.453L9.36017 18.5931C9.03061 18.713 8.66939 18.713 8.33983 18.5931L7.95459 18.453C5.36481 17.5113 3.20198 15.6664 1.86369 13.2575C1.75634 13.0642 1.7 12.8468 1.7 12.6258V5.75625C1.7 4.59718 2.45326 3.5726 3.55957 3.22688L8.05957 1.82063Z" fill="currentColor"/>
                    </svg>`,
                    // 右箭头（官方 bot-action）
                    chevron: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none"
                                   stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
                                   stroke-linejoin="round" width="100%" height="100%">
                        <path d="M6 3l5 5-5 5"/>
                    </svg>`,
                    // 钥匙形状太重，appId 用更轻的井号标签
                    hash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                                stroke-linecap="round" stroke-linejoin="round" width="100%" height="100%">
                        <path d="M4 9h16M4 15h16M10 3L8 21M16 3l-2 18"/>
                    </svg>`,
                    // 指令项：斜杠（command）
                    slash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"
                                 stroke-linecap="round" width="100%" height="100%">
                        <path d="M15 4L9 20"/>
                    </svg>`,
                    // 指令项：链接（link）
                    link: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                                stroke-linecap="round" stroke-linejoin="round" width="100%" height="100%">
                        <path d="M10 13a5 5 0 0 0 7.07 0l2-2a5 5 0 0 0-7.07-7.07l-1 1"/>
                        <path d="M14 11a5 5 0 0 0-7.07 0l-2 2a5 5 0 0 0 7.07 7.07l1-1"/>
                    </svg>`,
                    // 返回：左箭头
                    back: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"
                                stroke-linecap="round" stroke-linejoin="round"
                                style="width:13px;height:13px;display:block">
                        <path d="M10 3L5 8l5 5"/>
                    </svg>`,
                    // 备注：便签
                    note: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                                stroke-linecap="round" stroke-linejoin="round" width="100%" height="100%">
                        <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v9L14.5 21H6.5A2.5 2.5 0 0 1 4 18.5z"/>
                        <path d="M20 14.5h-4a1.5 1.5 0 0 0-1.5 1.5V21"/>
                        <path d="M8 8.5h8M8 12h5"/>
                    </svg>`
                },
                panels: [],
                // 各场景面板数：独立缓存，避免切换时沿用上一场景的数字
                scopeCounts: { c2c: 0, group: 0, channel: 0, dm: 0 },
                countsReady: false,
                loading: false,
                saving: false,
                showCreateModal: false,
                viewingPanel: null,
                editingPanel: null,
                // 拖拽状态：dragEnabled 仅在按下拖拽手柄后置位，
                // 否则整行 draggable 会吞掉输入框里的文本选择
                dragEnabled: false,
                dragIndex: null,
                dragOverIndex: null,
                uidSeq: 0,
                editForm: {
                    remark: '',
                    items: []
                },
                newPanel: {
                    remark: '',
                    items: []
                },

                async init() {
                    await this.loadBots();
                },

                async loadBots() {
                    this.botsLoading = true;
                    try {
                        const resp = await fetch('/api/bots');
                        if (!resp.ok) throw new Error(await this.errorMessage(resp));
                        const data = await resp.json();
                        this.bots = data.bots || [];
                    } catch (error) {
                        alert('加载机器人列表失败: ' + error.message);
                    } finally {
                        this.botsLoading = false;
                    }
                },

                async openBot(bot) {
                    this.activeBot = bot;
                    this.scope = 'group';
                    this.countsReady = false;
                    this.scopeCounts = { c2c: 0, group: 0, channel: 0, dm: 0 };
                    // 并发拉四个场景：既填好各自计数，也顺带拿到当前场景的列表
                    await this.loadAllScopes();
                },

                // 一次性拉全部场景，计数与当前列表同源，避免两者不一致
                async loadAllScopes() {
                    if (!this.activeBot) return;
                    this.loading = true;
                    try {
                        const results = await Promise.all(
                            this.scopes.map(s => this.fetchScope(s.value))
                        );
                        const counts = {};
                        results.forEach((records, i) => {
                            counts[this.scopes[i].value] = records.length;
                        });
                        this.scopeCounts = counts;
                        this.countsReady = true;
                        const idx = this.scopes.findIndex(s => s.value === this.scope);
                        this.panels = results[idx] || [];
                    } catch (error) {
                        alert('加载失败: ' + error.message);
                    } finally {
                        this.loading = false;
                    }
                },

                // 取单个场景的面板列表；失败按空列表处理，不阻断其它场景
                async fetchScope(scope) {
                    try {
                        const resp = await fetch(
                            `/api/bots/${this.activeBot.bot_id}/panels?scope=${scope}&limit=50`
                        );
                        if (!resp.ok) return [];
                        const data = await resp.json();
                        return data.records || [];
                    } catch {
                        return [];
                    }
                },

                // 切换场景：重新拉该场景列表（面板可能在别处被改动），
                // 计数由 loadPanels 内同步，切换过程中标签数字不会串场景
                async switchScope(value) {
                    if (this.scope === value) return;
                    this.scope = value;
                    await this.loadPanels();
                },

                backToBots() {
                    this.activeBot = null;
                    this.panels = [];
                    this.countsReady = false;
                },

                // channel / dm 仅支持全局配置，不能挂指定对象
                scopeHint() {
                    return ['channel', 'dm'].includes(this.scope)
                        ? '该场景仅支持全局配置（target_type=all），不能指定用户或群'
                        : '该场景支持全局或指定对象';
                },

                // QQ 服务端按显示宽度统计 name/desc（非 ASCII 计 2），
                // 而 maxlength 按 UTF-16 码元算，会漏放超长的中文串。
                width(text) {
                    let w = 0;
                    for (const ch of (text || '')) {
                        w += ch.codePointAt(0) < 128 ? 1 : 2;
                    }
                    return w;
                },

                // 返回第一条校验错误信息，无错则返回 null
                validateItems(items) {
                    if (items.length === 0) return '请至少添加一个指令项';
                    for (const [i, item] of items.entries()) {
                        const at = `第 ${i + 1} 项`;
                        if (!item.name) return `${at}缺少名称`;
                        if (!item.desc) return `${at}缺少描述`;
                        if (this.width(item.name) > 14) {
                            return `${at}「${item.name}」名称宽度 ${this.width(item.name)} 超过 14（中文计 2）`;
                        }
                        if (this.width(item.desc) > 30) {
                            return `${at}「${item.name}」描述宽度 ${this.width(item.desc)} 超过 30（中文计 2）`;
                        }
                        if (item.type === 'link' && !(item.link || '').startsWith('https://')) {
                            return `${at}「${item.name}」为链接类型，地址必须以 https:// 开头`;
                        }
                    }
                    return null;
                },

                async loadPanels() {
                    if (!this.activeBot) return;
                    this.loading = true;
                    try {
                        const resp = await fetch(
                            `/api/bots/${this.activeBot.bot_id}/panels?scope=${this.scope}&limit=50`
                        );
                        if (!resp.ok) throw new Error(await this.errorMessage(resp));
                        const data = await resp.json();
                        this.panels = data.records || [];
                        // 同步当前场景计数，保证增删后标签数字与列表一致
                        this.scopeCounts[this.scope] = this.panels.length;
                    } catch (error) {
                        alert('加载失败: ' + error.message);
                    } finally {
                        this.loading = false;
                    }
                },

                addPanelItem() {
                    if (this.newPanel.items.length >= 20) return;
                    this.newPanel.items.push({
                        name: '',
                        desc: '',
                        type: 'command',
                        only_admin: false,
                        link: null,
                        _uid: ++this.uidSeq
                    });
                },

                async createPanel() {
                    const err = this.validateItems(this.newPanel.items);
                    if (err) {
                        alert(err);
                        return;
                    }
                    try {
                        const resp = await fetch(`/api/bots/${this.activeBot.bot_id}/panels`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                scope: this.scope,
                                panel: {
                                    // 剔除前端内部的 _uid
                                    items: this.newPanel.items.map(i => ({
                                        name: i.name,
                                        desc: i.desc,
                                        type: i.type,
                                        only_admin: i.only_admin,
                                        link: i.type === 'link' ? i.link : null
                                    })),
                                    remark: this.newPanel.remark
                                },
                                target_type: 'all'
                            })
                        });
                        if (!resp.ok) throw new Error(await this.errorMessage(resp));
                        this.showCreateModal = false;
                        this.newPanel = { remark: '', items: [] };
                        await this.loadPanels();
                    } catch (error) {
                        alert('创建失败: ' + error.message);
                    }
                },

                viewPanel(panel) {
                    this.viewingPanel = panel;
                },

                startEdit(panel) {
                    // 深拷贝，避免编辑中直接改动列表里的对象——取消时应保持原样
                    this.editingPanel = panel;
                    this.editForm = {
                        remark: panel.panel.remark || '',
                        items: JSON.parse(JSON.stringify(panel.panel.items || []))
                            .map(i => ({ ...i, _uid: ++this.uidSeq }))
                    };
                },

                addEditItem() {
                    if (this.editForm.items.length >= 20) return;
                    this.editForm.items.push({
                        name: '',
                        desc: '',
                        type: 'command',
                        only_admin: false,
                        link: null,
                        _uid: ++this.uidSeq
                    });
                },

                moveItem(index, delta) {
                    const target = index + delta;
                    if (target < 0 || target >= this.editForm.items.length) return;
                    const items = this.editForm.items;
                    [items[index], items[target]] = [items[target], items[index]];
                },

                // ---- 拖拽排序（编辑与新建模态框共用）----
                // which: 'edit' 操作 editForm.items，'new' 操作 newPanel.items
                dragList(which) {
                    return which === 'new' ? this.newPanel.items : this.editForm.items;
                },

                onDragStart(index, event, which = 'edit') {
                    if (!this.dragEnabled) {
                        // 没按手柄就不允许拖，避免干扰输入框内的文本选择
                        event.preventDefault();
                        return;
                    }
                    this.dragIndex = index;
                    event.dataTransfer.effectAllowed = 'move';
                    // Firefox 需要 setData 才会真正启动拖拽
                    event.dataTransfer.setData('text/plain', String(index));
                },

                onDragOver(index) {
                    if (this.dragIndex === null) return;
                    this.dragOverIndex = index;
                },

                onDrop(index, which = 'edit') {
                    if (this.dragIndex === null || this.dragIndex === index) {
                        this.resetDrag();
                        return;
                    }
                    const items = this.dragList(which);
                    const [moved] = items.splice(this.dragIndex, 1);
                    items.splice(index, 0, moved);
                    this.resetDrag();
                },

                resetDrag() {
                    this.dragEnabled = false;
                    this.dragIndex = null;
                    this.dragOverIndex = null;
                },

                async saveEdit() {
                    const err = this.validateItems(this.editForm.items);
                    if (err) {
                        alert(err);
                        return;
                    }
                    this.saving = true;
                    try {
                        const url = `/api/bots/${this.activeBot.bot_id}/panels/${this.editingPanel.panel_id}`;
                        const resp = await fetch(url, {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                items: this.editForm.items.map(i => ({
                                    name: i.name,
                                    desc: i.desc,
                                    type: i.type,
                                    only_admin: i.only_admin,
                                    // 剔除前端内部的 _uid，并清掉非 link 类型的残留地址
                                    link: i.type === 'link' ? i.link : null
                                })),
                                remark: this.editForm.remark
                            })
                        });
                        if (!resp.ok) throw new Error(await this.errorMessage(resp));
                        this.editingPanel = null;
                        await this.loadPanels();
                    } catch (error) {
                        alert('保存失败: ' + error.message);
                    } finally {
                        this.saving = false;
                    }
                },

                async errorMessage(resp) {
                    // 后端把 QQ 侧业务错误转成 {detail, code, trace_id}
                    try {
                        const data = await resp.json();
                        if (typeof data.detail === 'string') return data.detail;
                        if (Array.isArray(data.detail)) {
                            return data.detail
                                .map(d => (d.msg || '').replace(/^Value error, /, ''))
                                .join('; ');
                        }
                        return JSON.stringify(data);
                    } catch {
                        return `HTTP ${resp.status}`;
                    }
                },

                async confirmDelete(panelId) {
                    if (!confirm(`确定要删除面板 ${panelId}？此操作不可逆。`)) return;
                    try {
                        const resp = await fetch(
                            `/api/bots/${this.activeBot.bot_id}/panels/${panelId}`,
                            { method: 'DELETE' }
                        );
                        if (!resp.ok) throw new Error(await this.errorMessage(resp));
                        await this.loadPanels();
                    } catch (error) {
                        alert('删除失败: ' + error.message);
                    }
                }
            };
        }
    </script>
</body>
</html>
"""
