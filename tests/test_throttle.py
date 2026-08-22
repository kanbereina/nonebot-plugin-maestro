"""WriteThrottler 单元测试（假时钟推进，不依赖真实时间）。"""

from nonebot_plugin_maestro.throttle import WriteThrottler


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_throttler(clock: FakeClock) -> WriteThrottler:
    return WriteThrottler(capacity=3, refill_per_minute=10, clock=clock)


class TestWriteThrottler:
    def test_allows_initial_burst(self):
        """桶容量 3：前三次连写放行。"""
        t = make_throttler(FakeClock())
        assert t.acquire("bot") == 0
        assert t.acquire("bot") == 0
        assert t.acquire("bot") == 0

    def test_fourth_rapid_write_waits(self):
        """桶空后第 4 次连写须等待约一个回填周期（60/10=6 秒）。"""
        clock = FakeClock()
        t = make_throttler(clock)
        for _ in range(3):
            assert t.acquire("bot") == 0
        wait = t.acquire("bot")
        assert wait > 0
        assert 5 < wait <= 6

    def test_refills_over_time(self):
        """等待满一个回填周期后应再次放行。"""
        clock = FakeClock()
        t = make_throttler(clock)
        for _ in range(4):
            t.acquire("bot")
        clock.advance(6)
        assert t.acquire("bot") == 0

    def test_partial_refill_shortens_wait(self):
        """等待 3 秒回填 0.5 个令牌，剩余等待应约 3 秒。"""
        clock = FakeClock()
        t = make_throttler(clock)
        for _ in range(4):
            t.acquire("bot")
        clock.advance(3)
        wait = t.acquire("bot")
        assert 2 < wait <= 3

    def test_keys_are_independent(self):
        """每个 bot 一个独立的桶，互不挤占。"""
        clock = FakeClock()
        t = make_throttler(clock)
        for _ in range(3):
            t.acquire("bot-a")
        assert t.acquire("bot-a") > 0
        assert t.acquire("bot-b") == 0

    def test_reset_clears_buckets(self):
        clock = FakeClock()
        t = make_throttler(clock)
        for _ in range(3):
            t.acquire("bot")
        t.reset()
        assert t.acquire("bot") == 0
