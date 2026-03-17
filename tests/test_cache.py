"""Tests for upsales_mcp.cache."""

from upsales_mcp import cache


class TestMakeKey:
    def test_different_args_different_keys(self):
        k1 = cache.make_key("test", "key1", "arg1")
        k2 = cache.make_key("test", "key1", "arg2")
        assert k1 != k2

    def test_different_api_keys_different_keys(self):
        k1 = cache.make_key("test", "key_a", "same_arg")
        k2 = cache.make_key("test", "key_b", "same_arg")
        assert k1 != k2

    def test_same_args_same_key(self):
        k1 = cache.make_key("test", "key1", "arg1", x=1)
        k2 = cache.make_key("test", "key1", "arg1", x=1)
        assert k1 == k2

    def test_prefix_in_key(self):
        k = cache.make_key("companies", "key1")
        assert k.startswith("companies:")

    def test_kwargs_affect_key(self):
        k1 = cache.make_key("test", "key1", limit=10)
        k2 = cache.make_key("test", "key1", limit=20)
        assert k1 != k2


class TestGetPut:
    def setup_method(self):
        cache.clear()

    def test_put_and_get(self):
        cache.put("k1", "value1")
        assert cache.get("k1") == "value1"

    def test_get_missing(self):
        assert cache.get("nonexistent") is None

    def test_expired_entry(self, monkeypatch):
        """Expired entries should return None."""
        # Insert at time 1000
        monkeypatch.setattr("upsales_mcp.cache.time.time", lambda: 1000.0)
        cache.put("k1", "value1")

        # Read at time 1000 + 301 (past 300s TTL)
        monkeypatch.setattr("upsales_mcp.cache.time.time", lambda: 1301.0)
        assert cache.get("k1") is None

    def test_not_expired(self, monkeypatch):
        """Entry within TTL should be returned."""
        monkeypatch.setattr("upsales_mcp.cache.time.time", lambda: 1000.0)
        cache.put("k1", "value1")

        monkeypatch.setattr("upsales_mcp.cache.time.time", lambda: 1299.0)
        assert cache.get("k1") == "value1"


class TestClear:
    def setup_method(self):
        cache.clear()

    def test_clear_empties_cache(self):
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        assert cache.get("k1") == "v1"
        cache.clear()
        assert cache.get("k1") is None
        assert cache.get("k2") is None
