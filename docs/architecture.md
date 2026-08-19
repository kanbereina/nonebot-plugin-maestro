# 架构说明

记录几个不那么直观、容易被后续改动误伤的设计决策。

## 插件加载与生命周期

`src/nonebot_plugin_maestro/__init__.py` 在**导入时**调用 `_setup()`，绑定四个 NoneBot 钩子：

- `on_bot_connect` — 注册该 bot 的面板客户端
- `on_bot_disconnect` — 移除
- `on_startup` — 启动 WebUI 的 uvicorn
- `on_shutdown` — 停止 uvicorn、清空注册表

这意味着宿主必须在 `register_adapter()` **之后**再 `load_plugin`，否则连接钩子绑定时适配器还不存在。

### `_setup()` 在未 init 时静默返回

```python
try:
    config = get_config()
except ValueError:
    # NoneBot has not been initialized
    return
```

这不是防御性编程的滥用——是真实需要。`get_plugin_config` 内部会 `nonebot.get_driver()`，NoneBot 未 `init()` 时抛 `ValueError`。如果不捕获，任何 `import nonebot_plugin_maestro.models` 之类的子模块导入都会被迫要求先 `nonebot.init()`，包括测试代码。测试直接用 `TestClient(app)`，完全不需要真实的 NoneBot 生命周期，不该被这个副作用拖住。

## WebUI 跑自己的 uvicorn，不挂 NoneBot 的 ASGI app

`WebUIServer`（`webui.py`）在 NoneBot 的事件循环里用 `asyncio.create_task` 起一个独立的 uvicorn 实例，监听 `MAESTRO_HOST:MAESTRO_PORT`（默认 `127.0.0.1:8100`）。

考虑过挂载到 NoneBot 的 ASGI app（`~fastapi` driver）作为子路由，放弃的理由：

- 会强制要求 driver 含 `~fastapi`，而适配器本身只需要 `HTTPClientMixin`（`~httpx`/`~websockets` 即可）。多数用户的 bot 未必用 fastapi driver。
- 端口耦合：WebUI 和 bot 的 webhook/API 混在一个端口上，用户想单独控制 WebUI 的访问范围（比如只内网访问）会更麻烦。
- 独立 uvicorn 用 `lifespan="off"`——它不需要 FastAPI 的 startup/shutdown 事件，那些职责已经由 NoneBot 的 `on_startup`/`on_shutdown` 钩子承担了，重复一份等于两套生命周期管理系统。

代价是多开一个端口，用默认值 `8100` 避开 NoneBot 的 `8080`，减少手动配置的必要。

## 配置读取：`Config` + `get_plugin_config`

早期版本手工解析 `driver.config.model_extra` 来读 `MAESTRO_*`。改成标准的 `Config`（pydantic 模型）+ `nonebot.get_plugin_config`，理由：

- 有类型校验（端口范围、字符串强转 int）
- 是发布规范推荐的做法，符合插件生态的一致性
- `model_extra` 的路径依赖 NoneBot 内部实现细节，`get_plugin_config` 是公开 API

## 前端拆分：静态文件而非内嵌字符串

`webui.py` 曾经把 1370 行 HTML/CSS/JS 内嵌成一个 Python 字符串（`return """..."""`）。现在拆到 `static/`：`index.html`、`app.css`、`app.js`，`index` 路由用 `FileResponse` 返回。

理由很直接：内嵌字符串没有语法高亮、没有 lint、编辑器把它当纯文本处理，1000+ 行的 HTML/JS 混在一个 Python docstring 里维护成本很高。

### 陷阱：`app.js` 必须排在 Alpine 的 `<script>` 之前

两者在 `index.html` 里都标了 `defer`，浏览器对 `defer` 脚本按**文档中的先后顺序**执行（而非加载完成的先后顺序）。如果 Alpine 排在前面，它初始化时 `maestroApp()` 尚未被 `app.js` 定义，页面会直接白屏，且浏览器控制台的报错不会直接指向这个顺序问题。

`tests/test_routes.py::TestIndex::test_app_js_precedes_alpine` 锁定了这个顺序，回归时测试会红。

## `BotRegistry`：类封装取代模块级 dict

`registry.py` 的 `BotRegistry` 包了一个 `dict[str, PanelAPIClient]`，而不是在 `webui.py` 里直接放一个模块级全局变量。好处主要是测试层面的：`items()`/`ids()` 返回快照（`list(...)`），调用方遍历时即使注册表被并发修改也不受影响；测试之间通过 `registry.clear()` 重置状态，比手动清空一个裸字典更不容易漏。

## `PanelAPIError` 与 `models.py` 不依赖 nonebot

`exceptions.py` 和 `models.py` 刻意不 import 任何 nonebot 相关模块。适配器抛出的 `ActionFailed`（nonebot-adapter-qq 的异常类型）在 `panel_client._call` 里被转换成 `PanelAPIError`，之后整条链路（`webui` 的 exception handler、测试里的假客户端）都只需要认识这一个不依赖外部库的异常类型。好处是测试假客户端可以直接 `raise PanelAPIError(...)`，不需要构造一个真实的适配器响应对象来触发 `ActionFailed`。
