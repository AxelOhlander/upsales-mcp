"""Tests for upsales_mcp.filters."""

import json

from upsales_mcp.filters import map_order_fields, parse_op, transform_filters


# --- parse_op ---


class TestParseOp:
    def test_gte(self):
        assert parse_op(">=100") == ("gte", "100")

    def test_lte(self):
        assert parse_op("<=50") == ("lte", "50")

    def test_gt(self):
        assert parse_op(">10") == ("gt", "10")

    def test_lt(self):
        assert parse_op("<5") == ("lt", "5")

    def test_ne(self):
        assert parse_op("!=0") == ("ne", "0")

    def test_eq_explicit(self):
        assert parse_op("=hello") == ("eq", "hello")

    def test_search(self):
        assert parse_op("*acme") == ("src", "acme")

    def test_plain_value(self):
        assert parse_op("plain") == ("eq", "plain")

    def test_plain_number(self):
        assert parse_op("42") == ("eq", "42")

    def test_date_value(self):
        assert parse_op(">=2026-03-16") == ("gte", "2026-03-16")


# --- transform_filters ---


class TestTransformFilters:
    def test_simple_string(self):
        result = transform_filters({"name": "*acme"})
        assert result == {"name": "src:acme"}

    def test_simple_int(self):
        result = transform_filters({"id": 42})
        assert result == {"id": 42}

    def test_simple_plain(self):
        result = transform_filters({"status": "open"})
        assert result == {"status": "open"}

    def test_multiple_simple(self):
        result = transform_filters({"name": "*acme", "id": ">=100"})
        assert result == {"name": "src:acme", "id": "gte:100"}

    def test_list_range_query(self):
        result = transform_filters({"date": [">=2026-03-16", "<=2026-03-22"]})
        assert "q[]" in result
        conditions = [json.loads(c) for c in result["q[]"]]
        assert {"a": "date", "c": "gte", "v": "2026-03-16"} in conditions
        assert {"a": "date", "c": "lte", "v": "2026-03-22"} in conditions

    def test_list_merges_simple_into_q(self):
        """When list values are present, simple filters also move to q[]."""
        result = transform_filters({"date": [">=2026-01-01"], "name": "*acme"})
        assert "q[]" in result
        # Simple filter should not be a top-level key
        assert "name" not in result
        conditions = [json.loads(c) for c in result["q[]"]]
        # The name filter appears in q[] with correct operator
        name_conds = [c for c in conditions if c["a"] == "name"]
        assert len(name_conds) == 1
        assert name_conds[0]["c"] == "src"
        assert name_conds[0]["v"] == "acme"

    def test_empty_filters(self):
        result = transform_filters({})
        assert result == {}

    def test_custom_field_equality(self):
        result = transform_filters({"custom.42": "2026-03-14"})
        assert result == {"custom": "eq:42:2026-03-14"}

    def test_custom_field_with_operator(self):
        result = transform_filters({"custom.42": ">=2026-04-14"})
        assert result == {"custom": "gte:42:2026-04-14"}

    def test_custom_field_search(self):
        result = transform_filters({"custom.11": "*SaaS"})
        assert result == {"custom": "src:11:SaaS"}

    def test_custom_field_range(self):
        result = transform_filters({"custom.42": [">=2026-01-01", "<=2026-12-31"]})
        assert result["custom"] == ["gte:42:2026-01-01", "lte:42:2026-12-31"]

    def test_custom_field_with_regular_filters(self):
        result = transform_filters({"name": "*Acme", "custom.42": "2026-03-14"})
        assert result["name"] == "src:Acme"
        assert result["custom"] == "eq:42:2026-03-14"

    def test_custom_field_with_q_conditions(self):
        """Custom fields stay separate from q[] conditions."""
        result = transform_filters(
            {
                "date": [">=2026-01-01", "<=2026-12-31"],
                "custom.42": "test",
            }
        )
        assert "q[]" in result
        assert result["custom"] == "eq:42:test"

    def test_multiple_custom_fields(self):
        result = transform_filters({"custom.42": "val1", "custom.11": "val2"})
        assert isinstance(result["custom"], list)
        assert "eq:42:val1" in result["custom"]
        assert "eq:11:val2" in result["custom"]


# --- map_order_fields ---


class TestMapOrderFields:
    def test_maps_value(self):
        assert map_order_fields(["value", "id"]) == ["orderValue", "id"]

    def test_passthrough(self):
        assert map_order_fields(["description", "date"]) == ["description", "date"]

    def test_none(self):
        assert map_order_fields(None) is None

    def test_empty_list(self):
        assert map_order_fields([]) == []
