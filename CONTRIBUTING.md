# 贡献指南

感谢你对 Maestro 感兴趣。本文档说明如何搭建开发环境、提交改动、以及项目的一些约定。

## 开发环境

依赖与运行统一走 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/kanbereina/nonebot-plugin-maestro.git
cd nonebot-plugin-maestro
uv sync                # 安装依赖（含 dev 组）
```

本地起一个 bot 调试插件：

```bash
cp .env.example .env   # 填入 QQ_BOTS 等配置
uv run python bot.py
```

`bot.py` 只在本仓库用于调试，不会随插件发布——它不是 `src/` 的一部分。

## 提交前的检查

三项都要过，CI 会重复跑一遍：

```bash
uv run poe lint        # ruff check
uv run poe format      # ruff format
uv run poe typecheck   # pyrefly check（strict 预设）
uv run poe test        # pytest（含覆盖率）
```

单独跑一个测试：

```bash
uv run pytest tests/test_validation.py::test_display_width -q
```

如果装了 [pre-commit](https://pre-commit.com/)，`ruff-check`/`ruff-format`/`uv-lock` 会在提交时自动跑：

```bash
pre-commit install
```

## 测试原则

**面板写接口会真实修改线上面板且不可逆**——`tests/` 里全部用假客户端（见 `tests/test_routes.py` 的 `FakeClient`），任何新增测试都不能打真实 QQ API。

- 纯逻辑（`validation.py`、`models.py`、`config.py`、`exceptions.py`）直接单测，不需要 mock
- 路由测试用 `fastapi.testclient.TestClient` + 假客户端，不经 NoneBot 生命周期
- `registry.py` 的测试用最小假对象（只提供 `bot.self_id`），不引入真实 `PanelAPIClient`

## 代码风格

- Python 3.12+ 语法：`ruff` 的 `UP` 规则会拦截 `typing.Sequence`、`Optional[X]` 这类旧写法，直接用 `collections.abc.Sequence`、`X | None`
- `pyrefly` 是 strict 预设：新代码写全类型标注，参数不允许隐式 `Any`
- 默认不写注释；只在解释"为什么这样做"（而非"这段代码做什么"）时才加，尤其是踩过坑、或行为与直觉相悖的地方
- 前端资源（`static/index.html`/`app.css`/`app.js`）保持独立文件，不要内嵌回 Python

## 提交信息

用 [Conventional Commits](https://www.conventionalcommits.org/)：`feat:`、`fix:`、`refactor:`、`ci:`、`chore:`、`docs:`、`test:`。看 `git log` 里的历史提交能直接对齐风格。

## PR 流程

1. 从 `main` 切分支，不要直接推 `main`
2. 确保上面的检查全过
3. PR 描述里说明改了什么、为什么改（而非机械复述 diff）；涉及行为变化时附上你验证过的证据（命令输出、测试结果），不要只写"应该可以"
4. 仓库启用了 ruleset 禁止强制推送到受保护分支；CI（ruff / pyrefly / pytest 矩阵 / 插件加载测试）全绿后才会合并

## 深入了解项目

[`docs/`](docs/README.md) 目录收录了面板 API 的实测细节、常见陷阱、架构决策的取舍理由——这些内容比 README 更技术化，改动 `panel_client.py`、`validation.py` 或校验逻辑之前建议先看一遍，能避开几个已经踩过的坑（比如错误码 `30013` 的误导性、显示宽度和 `len()` 的差异）。

## 报告问题

Bug 用 [bug 反馈模板](.github/ISSUE_TEMPLATE/bug-report.yml)，功能建议用 [功能建议模板](.github/ISSUE_TEMPLATE/feature-request.yml)。提交前搜索一下是否已有相同 issue。

**不要在 issue 或 PR 里粘贴 `QQ_BOTS` 的 token / secret**——那是机器人凭证，泄露后请立即在 QQ 开放平台重置。
