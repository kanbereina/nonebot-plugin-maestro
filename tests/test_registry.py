"""BotRegistry 测试。

注册表用类封装取代模块级 dict，读写入口集中；测试用假客户端，
不触碰真实 QQ API。
"""

from typing import Any

import pytest

from nonebot_plugin_maestro.registry import BotRegistry


class FakeBot:
    def __init__(self, self_id: str) -> None:
        self.self_id = self_id


class FakeClient:
    """只提供 registry 用到的 bot.self_id。"""

    def __init__(self, self_id: str) -> None:
        self.bot = FakeBot(self_id)


def make_client(self_id: str) -> Any:
    return FakeClient(self_id)


@pytest.fixture
def registry() -> BotRegistry:
    return BotRegistry()


class TestAddAndGet:
    def test_starts_empty(self, registry: BotRegistry):
        assert len(registry) == 0
        assert registry.ids() == []

    def test_add_then_get(self, registry: BotRegistry):
        client = make_client("102072450")
        registry.add(client)
        assert len(registry) == 1
        assert registry.get("102072450") is client

    def test_get_missing_returns_none(self, registry: BotRegistry):
        assert registry.get("nonexistent") is None

    def test_contains(self, registry: BotRegistry):
        registry.add(make_client("a"))
        assert "a" in registry
        assert "b" not in registry

    def test_add_same_id_overwrites(self, registry: BotRegistry):
        """重连时应替换旧客户端，而非累积。"""
        first = make_client("a")
        second = make_client("a")
        registry.add(first)
        registry.add(second)
        assert len(registry) == 1
        assert registry.get("a") is second


class TestRemoveAndClear:
    def test_remove(self, registry: BotRegistry):
        registry.add(make_client("a"))
        registry.remove("a")
        assert len(registry) == 0

    def test_remove_missing_is_noop(self, registry: BotRegistry):
        """断开钩子可能对未注册的 bot 触发，不应抛异常。"""
        registry.remove("nonexistent")  # 不抛异常
        assert len(registry) == 0

    def test_clear(self, registry: BotRegistry):
        registry.add(make_client("a"))
        registry.add(make_client("b"))
        registry.clear()
        assert len(registry) == 0


class TestSnapshot:
    def test_items_returns_snapshot(self, registry: BotRegistry):
        """items() 返回快照：调用方遍历时若有增删不应受影响。"""
        registry.add(make_client("a"))
        snapshot = registry.items()
        registry.add(make_client("b"))
        assert len(snapshot) == 1  # 快照未被后续写入影响
        assert len(registry.items()) == 2

    def test_ids_returns_snapshot(self, registry: BotRegistry):
        registry.add(make_client("a"))
        ids = registry.ids()
        registry.clear()
        assert ids == ["a"]
