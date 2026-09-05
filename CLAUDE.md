# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

Maestro 是适用 NoneBot2 的**可视化指令面板管理工具**：在本地端口启动一个 WebUI，让开发者以图形方式修改、预览、保存 QQ 官方机器人的指令面板（命令菜单），面板数据最终通过 QQ OpenAPI `/v2/panels` 系列接口落库。

依赖的两个外部契约：
- QQ 适配器：<https://github.com/nonebot/adapter-qq>（PyPI `nonebot-adapter-qq`）
- 指令面板接口文档：<https://bot.q.qq.com/wiki/develop/api-v2/server-inter/menu-panel/>

## 代码结构

这是一个 **NoneBot 插件**（按发布规范命名）：包名 `nonebot-plugin-maestro`，模块 `nonebot_plugin_maestro`。当前分支 `master`，PR 目标分支 `main`。

| 文件 | 职责 |
|---|---|
| `src/nonebot_plugin_maestro/__init__.py` | `__plugin_meta__` + `_setup()`（导入时绑定生命周期钩子） |
| `.../webui.py` | FastAPI 路由 + `WebUIServer`（托管独立 uvicorn） |
| `.../panel_client.py` | `PanelAPIClient`：面板 API 调用 |
| `.../models.py` | pydantic 模型（不依赖 nonebot） |
| `.../config.py` | `Config`（pydantic）+ `get_config()` |
| `.../registry.py` | `BotRegistry`：已连接 bot 的客户端注册表 |
| `.../logger.py` | `get_logger()`，统一走 nonebot logger |
| `.../exceptions.py` | `PanelAPIError`（不依赖 nonebot） |
| `.../validation.py` | 显示宽度校验 |
| `.../static/` | 前端：`index.html` / `app.css` / `app.js` / 图标 |
| `bot.py` | **仅本地开发调试用**，发布后用户不需要 |

**前端资源不要内嵌回 Python**。`webui.py` 曾内嵌 1370 行 HTML/CSS/JS，已拆为 `static/` 下的独立文件，`index` 路由用 `FileResponse` 返回。

⚠️ `static/index.html` 里 **`app.js` 必须排在 Alpine 的 script 标签之前**：两者同为 `defer`，按文档顺序执行，若 Alpine 先跑则 `maestroApp()` 尚未定义、页面白屏。已有测试锁定此顺序。

**倾向类封装而非模块级全局**：状态（如 bot 注册表）用类实例持有，工具函数按职责归入类方法。

### 插件加载与配置

`__init__.py` 在**导入时**调用 `_setup()` 绑定钩子（`on_bot_connect` 注册客户端、`on_startup` 起 uvicorn）。因此宿主须在 `register_adapter()` **之后**再 `load_plugin`。

`_setup()` 在 NoneBot 未 init 时静默返回——这样 `models`/`validation` 等子模块可被独立导入（测试依赖此行为），不强制先 init。

配置走标准插件方式：`Config`（pydantic 模型）+ `nonebot.get_plugin_config`，`.env` 中以 `MAESTRO_` 前缀配置，全部字段有默认值（发布规范要求零配置可加载）。**不要**改回手工解析 `driver.config.model_extra`。

WebUI 跑在自己的 uvicorn 上（默认 `127.0.0.1:8100`，避开 NoneBot 的 8080），不挂载到 NoneBot 的 ASGI app，因此 driver **不需要** `~fastapi`。

### 依赖

`nonebot2`、`httpx[http2]` 与 `nonebot-adapter-qq` 都是**必需依赖**，不是 extra——各模块直接 import 它们，缺任一者插件无法加载。`uv sync` 即可。注意 nonebot2 声明为裸依赖（不带 `[httpx,websockets]` extra）：httpx 驱动实现库由插件直接声明，避免向宿主编排透出 extras；websockets 驱动库未直接声明（插件的 HTTP 客户端不需要它，需要时由宿主的 driver 配置自行引入）。

### 工程化

```bash
uv run poe test      # pytest + 覆盖率
uv run poe lint      # ruff check
uv run poe typecheck # pyrefly（strict）
uv run pytest -q     # 快速跑测试
```

测试全部用假客户端，**不打真实 QQ API**——面板写接口会真实修改线上面板且不可逆。CI（`.github/workflows/ci.yml`）跑 ruff、pyrefly、pytest（3.12/3.13）与插件加载测试。

## 常用命令

包管理与运行统一走 uv（构建后端也是 `uv_build`，不是 setuptools/hatch）：

```bash
uv sync                        # 按 uv.lock 同步依赖（含 dev 组）
uv add <pkg>                   # 加运行时依赖，会同时更新 uv.lock
uv add --dev <pkg>             # 加开发依赖
uv run ruff check .            # lint
uv run ruff check --fix .      # lint 并自动修
uv run ruff format .           # 格式化
uv run pyrefly check           # 类型检查（strict 预设）
```

Python 版本：`requires-python = ">=3.12, <3.14"`，当前 venv 是 3.12.10。写代码按 3.12+ 语法下限，`ruff` 已 `extend-select = ["UP"]`，会拦截 `typing.Sequence`、`Optional[X]` 这类旧写法——直接用 `collections.abc.Sequence`、`X | None`。

`pyrefly` 用 `preset = "strict"`：参数与类型实参不允许隐式 `Any`、空容器需标注、覆写需 `@override`。新代码一律写全类型标注。

测试已建立（`tests/`，80 个用例）：`uv run pytest -q` 或 `uv run poe test`（带覆盖率）；单测单跑 `uv run pytest tests/test_x.py::test_y -q`。全部用假客户端，**不打真实 QQ API**。

## 架构要点

### 关键约束：适配器没有包装面板接口

我已核对 adapter-qq `master` 全部源码（`bot.py`、`adapter.py`、`models/*`），**不区分大小写搜索 "panel" 零命中**。`Bot` 类覆盖了频道/成员/消息/C2C/群消息等接口，但**完全没有 `/v2/panels` 的封装方法**。

因此面板读写必须走适配器的通用请求出口：

```python
from nonebot.drivers import (
    Request,
)  # 注意是 nonebot.drivers.Request，不是 httpx.Request

resp = await bot._request(
    Request("GET", api_base / "v2/panels", params={"scope": "group"})
)
```

`Bot._request(request: Request) -> Any` 会自动注入鉴权头、经 `adapter.request()` 派发、把失败包成 `NetworkError`，并在 401 时清缓存换取新 token 后**自动重试一次**。它带前导下划线（非公开 API），是当前唯一可行路径——把它收敛到一个独立的面板 API 客户端模块里，别散落在各处调用，将来适配器补上官方封装时只改一处。

### 鉴权与环境

token 逻辑就在 `Bot` 类上（无独立 token 管理模块）：`get_access_token` 缓存 token 与过期时间，仅在无缓存或距过期 30s 内才刷新。

- 鉴权头：`Authorization: QQBot <access_token>`，并附 `X-Union-Appid: <bot id>`
- 取 token：`POST https://bots.qq.com/app/getAppAccessToken`（`appId` + `clientSecret`）

⚠️ **域名已统一，适配器落后于官方文档。** 官方变更记录 20260810 起所有接口域名统一为 `api.bot.qq.com`，沙箱/生产不再分流；指令面板接口是 20260812 才新增的。但 adapter-qq 仍按 `qq_is_sandbox` 在 `api.sgroup.qq.com` / `sandbox.api.sgroup.qq.com` 间切换（`Adapter.get_api_base()`）。

实测两个域名对面板接口**行为一致**（同样的请求得到同样的成功/失败结果），因此旧域名目前仍可用，`sandbox` 配置已无隔离效果——**不要依赖 `QQ_IS_SANDBOX=true` 来保护线上面板，它打的仍是同一份真实数据**。改动面板前先确认目标账号。

NoneBot 侧配置字段（`.env`）：`QQ_IS_SANDBOX`、`QQ_BOTS`（JSON 数组，元素含 `id` / `token` / `secret`，可选 `intent`、`use_websocket`）、`QQ_API_BASE`、`QQ_SANDBOX_API_BASE`、`QQ_AUTH_BASE`。需要显式指定新域名时可覆盖 `QQ_API_BASE`。

**driver 必须提供 HTTP 客户端**：适配器 `setup()` 强制要求 `HTTPClientMixin`，NoneBot 默认的 `~fastapi` 不满足会直接抛错。`webui.py` 里已固定 `nonebot.init(driver="~httpx+~websockets")`，不读 `.env` 的 `DRIVER`。

### 面板接口一览

| 方法 | 路径 | 用途 | 限频 |
|---|---|---|---|
| GET | `/v2/panels` | 列表（游标翻页） | 30 QPM |
| POST | `/v2/panels` | 创建，返回 `panel_id` | 10 QPM |
| GET | `/v2/panels/{panel_id}` | 详情 | 30 QPM |
| PUT | `/v2/panels/{panel_id}` | 改面板内容，返回新 `version` | 10 QPM |
| DELETE | `/v2/panels/{panel_id}` | 删除 | 10 QPM |
| PUT | `/v2/panels/{panel_id}/target` | 增删关联对象（`op` = `add`/`del`） | 60 QPM |

写接口只有 10 QPM，WebUI 的保存动作要做节流/合并，别让界面上的每次编辑都直连接口。

### 数据模型

`Panel` = `{ items: PanelItem[], remark: string, version: int }`；
`PanelItem` = `{ name, desc, type, only_admin, link }`，`type` 取 `command` 或 `link`。

面板记录还带 `panel_id`、`scope`、`target_type`、`created_at` / `updated_at`（RFC3339）、`version`，详情接口额外返回 `user_openids` / `group_openids`。

维度组合规则：
- `scope`：`c2c`（私聊）、`group`（群）、`channel`（文字子频道）、`dm`（频道私信）
- `target_type`：`all`（全局）或 `specific`（指定用户/群）
- **只有 `c2c` 和 `group` 支持 `specific`；`channel` 和 `dm` 仅支持 `all`**。`target_type=all` 的面板不能再挂具体关联对象（否则报 40030021），`/target` 接口在 `channel`/`dm` 场景不支持（40030018）。

### 校验规则（WebUI 前端与后端都要挡）

- 每个机器人最多 **20 个面板**（跨所有 scope 合计，非每场景 20）；每个面板最多 **20 个 item**
- `name` 显示宽度 ≤ 14；`desc` 显示宽度 ≤ 30；`remark` ≤ 255 字符（仅开发者可见）
- `type=link` 的 `link` **必须以 `https://` 开头**
- 关联对象：单次请求最多 20 个 openid，单面板累计上限 1000 个；列表接口 `limit` 默认 20、最大 50

⚠️ **已实测确认：`name`/`desc` 按显示宽度计数，非 `len()`。** 非 ASCII 字符算 2。

实测样本（2026-08-19，生产环境）：`desc="解析哔哩哔哩视频，转换为MP3或FLAC格式音频"` 被拒。该串 `len()=21 < 30`，但宽度 = 16×2 + 3 + 4 + 2×2 = 43 > 30。同批测试中 4 个 item 正常保存，确认与数量无关。

**踩坑点**：浏览器 `maxlength` 按 UTF-16 码元计数，挡不住这种超宽中文串（21 < 30 直接放过），服务端才拒。校验统一走 `nonebot_plugin_maestro.validation.display_width`，前端有对应的 `width()` 实现与实时计数显示。

### 错误码

文档列出的码带 `4003` 前缀（`40030006` 面板不存在 · `40030008` URL 格式错误 · `40030009` 面板操作中请稍后重试 · `40030011` scope 非法 · `40030012` target_type 非法 · `40030013` 数量超限 · `40030015` item 类型非法 · `40030016` 必填字段缺失 · `40030018` 当前场景不支持 · `40030020` 内容存在安全风险 · `40030021` 全局面板不支持指定关联）。

⚠️ **实测返回值与文档双重不一致，排查时务必注意：**

1. **无 `4003` 前缀**：实际返回 `code=30013`、`code=30016`，HTTP 400。
2. **`30013` 语义被复用且具有误导性**：字面是「超出数量限制」，但**字段显示宽度超限也返回它**。曾因此误判为面板数量或 item 数量超限，实际是单个 `desc` 过长。遇到 `30013` 先查字段宽度，再查数量。

因此**不要按 code 精确匹配做分支判断**，优先透传服务端 `message`，并记录 `X-Tps-trace-ID`（响应头）。

QQ 侧业务错误由 `panel_client._call` 统一捕获 `ActionFailed` 并转成 `nonebot_plugin_maestro.exceptions.PanelAPIError`，再由 `webui` 的 exception handler 输出 4xx + 原始 message。`exceptions.py` 与 `validation.py` 不依赖 nonebot，使异常处理与 QQ 侧类型解耦。新增接口调用请走 `_call`，不要直接用 `bot._request`，否则错误会漏成 500 + traceback。

`version` 字段是乐观并发的抓手：`PUT` 返回修改后的版本号，WebUI 应携带并比对版本，防止多端编辑互相覆盖。注意 `version` 在请求体中是**可选**的，实测传/不传、传 0 都能成功，服务端未强制校验版本匹配——乐观并发需自行在应用层实现。

## 其他

- 面板是**远端账号级状态**，不是本地文件。删除/覆盖面板不可逆且立即对所有用户生效——涉及 `DELETE /v2/panels/{id}` 或对线上（非沙箱）面板执行 `PUT` 时，先向用户确认。
- WebUI 绑定本地端口，默认应只监听 `127.0.0.1`；一旦要对外暴露或加上写接口，必须同时给出鉴权方案，别留未认证的写入口。
