"""Maestro 异常类型。

不依赖 nonebot：适配器的 ActionFailed 在 panel_client 边界处被转换成这里的
PanelAPIError，使 webui 的异常处理器与 QQ 侧异常类型解耦。
"""

from typing import override


class PanelAPIError(Exception):
    """QQ 指令面板接口返回的业务错误。

    对应 QQ OpenAPI 的非 2xx 响应（如数量超限、面板不存在、场景不支持）。
    这类错误是调用方输入或账号状态问题，不是服务端故障，应以 4xx 回给前端。
    """

    def __init__(
        self,
        status_code: int,
        code: int | None = None,
        message: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.trace_id = trace_id
        super().__init__(self.describe())

    def describe(self) -> str:
        """人类可读的错误描述（用于前端展示）。"""
        parts: list[str] = []
        if self.message:
            parts.append(self.message)
        if self.code is not None:
            parts.append(f"错误码 {self.code}")
        if not parts:
            parts.append(f"HTTP {self.status_code}")
        return "，".join(parts)

    @override
    def __repr__(self) -> str:
        return (
            f"<PanelAPIError status={self.status_code} code={self.code} "
            f"message={self.message!r} trace_id={self.trace_id}>"
        )
