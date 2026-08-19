<div align="center">
<img src="src/nonebot_plugin_maestro/static/maestro.svg" width="160" height="160" alt="Maestro logo">

# Maestro

**QQ 官方机器人指令面板可视化管理工具**

在本地启动一个 WebUI，用图形界面查看、编辑、保存 QQ 机器人的指令面板。

</div>

## 简介

QQ 官方机器人的指令面板（用户在聊天框看到的命令菜单）只能通过 [OpenAPI](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/menu-panel/) 管理，没有官方可视化界面。Maestro 作为 NoneBot 插件随 bot 启动，提供一个本地 WebUI 来做这件事：

- 多机器人卡片，按 `QQ_BOTS` 配置逐个列出
- 四种场景（群聊 / 私聊 / 频道 / 频道私信）分别管理，标签页显示各自面板数
- 指令项增删改、拖拽排序
- 提交前本地校验：显示宽度、`https` 链接、数量上限
- QQ 侧业务错误转成可读提示，不再是 `500 Internal Server Error`

## 安装

<details open>
<summary>nb-cli</summary>

```bash
nb plugin install nonebot-plugin-maestro
```

</details>

<details>
<summary>包管理器</summary>

```bash
uv add nonebot-plugin-maestro
# 或
pip install nonebot-plugin-maestro
```

安装后在 `pyproject.toml` 的 `[tool.nonebot]` 中加载：

```toml
plugins = ["nonebot_plugin_maestro"]
```

</details>

## 配置

在宿主 bot 的 `.env` 中配置。**全部可选**，插件支持零配置加载。

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `MAESTRO_HOST` | `127.0.0.1` | WebUI 监听地址 |
| `MAESTRO_PORT` | `8100` | WebUI 监听端口 |
| `MAESTRO_ENABLED` | `true` | 是否启用 WebUI |

WebUI 跑在自己的 uvicorn 上，端口与 NoneBot 的 `PORT` 相互独立（默认 8100 就是为了避开 NoneBot 的 8080）。

driver 需提供 HTTP 客户端——适配器 `setup()` 强制要求 `HTTPClientMixin`：

```dotenv
DRIVER=~httpx+~websockets
```

> [!WARNING]
> WebUI **没有鉴权**。默认只监听 `127.0.0.1`，仅本机可访问。若改为 `0.0.0.0`，面板的写接口（含删除）会暴露到网络上，请自行加访问控制。

## 使用

bot 启动后访问 <http://127.0.0.1:8100>。机器人 WebSocket 连接成功后才会出现在列表中。

> [!CAUTION]
> 面板是**远端账号级状态**，不是本地文件。删除与覆盖不可逆，且立即对所有用户生效。

## 注意事项

**字段长度按显示宽度计算**，不是字符数。QQ 服务端对非 ASCII 字符计 2：`name` ≤ 14、`desc` ≤ 30。

超限时服务端返回 `code=30013`「超出数量限制」——这个错误码同时用于数量超限，容易误判。WebUI 会实时显示宽度并在提交前拦截。

**写接口限频 10 QPM**（创建 / 修改 / 删除），每个机器人最多 20 个面板（跨场景合计）。

## 开发

```bash
uv sync              # 安装依赖
uv run poe test      # 测试（含覆盖率）
uv run poe lint      # ruff 检查
uv run poe typecheck # pyrefly 类型检查
uv run python bot.py # 本地起一个 bot 调试
```

前端资源在 `src/nonebot_plugin_maestro/static/`（`index.html` / `app.css` / `app.js`），不内嵌在 Python 里。

想贡献代码？看 [CONTRIBUTING.md](CONTRIBUTING.md)。面板接口的实测细节与架构决策见 [docs/](docs/README.md)。

## 许可

[MIT](LICENSE)
