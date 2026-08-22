"""写接口限速。

QQ 写接口配额 10 QPM（见 docs/panel-api.md）；前端虽已有 saving 标志
与确认弹窗，连点仍会瞬间打满配额，之后一段时间内所有写操作被 QQ
拒绝且错误信息不直观。本地用令牌桶提前拦成 429，把「不明所以的
失败」变成「明确的稍后重试」。
"""

import time
from collections.abc import Callable


class WriteThrottler:
    """按 key（bot id）独立的令牌桶。

    容量 3、每分钟回填 10：允许连续编辑两三个面板的小突发，持续
    速率压在 QQ 配额内。时钟可注入，测试用假时钟推进。
    """

    def __init__(
        self,
        capacity: float = 3.0,
        refill_per_minute: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._capacity = capacity
        self._rate = refill_per_minute / 60.0  # 每秒回填
        self._clock = clock
        self._tokens: dict[str, float] = {}
        self._last: dict[str, float] = {}

    def acquire(self, key: str) -> float:
        """取一个令牌；返回 0 表示成功，否则返回需等待的秒数（不等待）。"""
        now = self._clock()
        tokens = min(
            self._capacity,
            self._tokens.get(key, self._capacity)
            + (now - self._last.get(key, now)) * self._rate,
        )
        self._last[key] = now
        if tokens >= 1.0:
            self._tokens[key] = tokens - 1.0
            return 0.0
        self._tokens[key] = tokens
        return (1.0 - tokens) / self._rate

    def reset(self) -> None:
        """清空各 key 的桶（测试用）。"""
        self._tokens.clear()
        self._last.clear()
