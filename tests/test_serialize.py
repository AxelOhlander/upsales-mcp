"""Tests for upsales_mcp.serialize."""

import json

from upsales_mcp.serialize import serialize


class MockModel:
    """Minimal mock of a Pydantic model with model_dump()."""

    def __init__(self, data: dict):
        self._data = data

    def model_dump(self, *, mode="json", by_alias=True, exclude=None):
        if exclude:
            return {k: v for k, v in self._data.items() if k not in exclude}
        return dict(self._data)


class TestSerialize:
    def test_basic_single_model(self):
        model = MockModel({"id": 1, "name": "Acme"})
        result = json.loads(serialize(model))
        assert result == {"id": 1, "name": "Acme"}

    def test_basic_list(self):
        models = [MockModel({"id": 1, "name": "A"}), MockModel({"id": 2, "name": "B"})]
        result = json.loads(serialize(models))
        assert len(result) == 2
        assert result[0]["name"] == "A"
        assert result[1]["name"] == "B"

    def test_field_selection_keeps_id(self):
        model = MockModel({"id": 1, "name": "Acme", "phone": "555"})
        result = json.loads(serialize(model, fields=["name"]))
        assert result == {"id": 1, "name": "Acme"}
        assert "phone" not in result

    def test_field_selection_multiple(self):
        model = MockModel({"id": 1, "name": "Acme", "phone": "555", "city": "NYC"})
        result = json.loads(serialize(model, fields=["name", "city"]))
        assert set(result.keys()) == {"id", "name", "city"}

    def test_metadata_wrapping(self):
        models = [MockModel({"id": 1, "name": "A"})]
        meta = {"total": 10, "count": 1}
        result = json.loads(serialize(models, metadata=meta))
        assert result["metadata"] == {"total": 10, "count": 1}
        assert len(result["data"]) == 1
        assert result["data"][0]["name"] == "A"

    def test_null_stripping(self):
        model = MockModel({"id": 1, "name": "Acme", "phone": None, "tags": []})
        result = json.loads(serialize(model))
        assert "phone" not in result
        assert "tags" not in result

    def test_empty_string_stripping(self):
        model = MockModel({"id": 1, "notes": ""})
        result = json.loads(serialize(model))
        assert "notes" not in result

    def test_empty_dict_stripping(self):
        model = MockModel({"id": 1, "address": {}})
        result = json.loads(serialize(model))
        assert "address" not in result

    def test_nested_exclude(self):
        model = MockModel(
            {
                "id": 1,
                "orderRow": [
                    {
                        "product": "Widget",
                        "quantity": 2,
                        "sortId": 1,
                        "custom": {"x": 1},
                        "purchaseCost": 50,
                    }
                ],
            }
        )
        result = json.loads(serialize(model))
        row = result["orderRow"][0]
        assert row["product"] == "Widget"
        assert row["quantity"] == 2
        assert "sortId" not in row
        assert "custom" not in row
        assert "purchaseCost" not in row

    def test_exclude_fields_applied(self):
        """Top-level exclude fields from EXCLUDE_FIELDS should be stripped by model_dump."""
        model = MockModel({"id": 1, "name": "Acme", "custom_fields": [1, 2]})
        result = json.loads(serialize(model))
        assert "custom_fields" not in result

    def test_nested_dict_cleaned(self):
        model = MockModel(
            {
                "id": 1,
                "metadata": {
                    "agreementNotes": "internal",
                    "startDate": "2026-01-01",
                    "versionNo": 3,
                },
            }
        )
        result = json.loads(serialize(model))
        meta = result["metadata"]
        assert "agreementNotes" not in meta
        assert "versionNo" not in meta
        assert meta["startDate"] == "2026-01-01"

    def test_dot_notation_fields_keep_parent(self):
        """Dot-notation fields like 'orderRow.product.id' should keep the top-level key."""
        model = MockModel(
            {
                "id": 1,
                "description": "Test order",
                "value": 1000,
                "orderRow": [{"product": {"id": 5, "name": "Widget"}, "quantity": 2, "price": 500}],
            }
        )
        result = json.loads(
            serialize(
                model, fields=["orderRow.product.id", "orderRow.product.name", "orderRow.price"]
            )
        )
        assert "orderRow" in result
        assert "id" in result
        assert "description" not in result
        assert "value" not in result

    def test_dot_notation_mixed_with_flat_fields(self):
        """Mix of flat and dot-notation fields should work together."""
        model = MockModel(
            {
                "id": 1,
                "description": "Test",
                "value": 500,
                "orderRow": [{"product": {"id": 1}, "price": 100}],
            }
        )
        result = json.loads(serialize(model, fields=["value", "orderRow.product.id"]))
        assert set(result.keys()) == {"id", "value", "orderRow"}


class TestCustomFieldResolution:
    DEFS = {
        42: {"name": "Delivery Date", "type": "Date", "alias": "DELIVERY"},
        11: {"name": "Industry", "type": "Select", "alias": "INDUSTRY"},
    }

    def test_resolves_custom_fields(self):
        model = MockModel(
            {
                "id": 1,
                "name": "Acme",
                "custom": [
                    {"fieldId": 42, "value": None, "valueDate": "2026-03-14"},
                    {"fieldId": 11, "value": "SaaS"},
                ],
            }
        )
        result = json.loads(serialize(model, custom_field_defs=self.DEFS))
        assert "customFields" in result
        assert result["customFields"]["Delivery Date"] == {
            "value": "2026-03-14",
            "fieldId": 42,
            "type": "Date",
        }
        assert result["customFields"]["Industry"] == {
            "value": "SaaS",
            "fieldId": 11,
            "type": "Select",
        }
        assert "custom" not in result

    def test_skips_unknown_field_ids(self):
        model = MockModel(
            {
                "id": 1,
                "custom": [{"fieldId": 999, "value": "unknown"}],
            }
        )
        result = json.loads(serialize(model, custom_field_defs=self.DEFS))
        assert "customFields" not in result

    def test_skips_null_values(self):
        model = MockModel(
            {
                "id": 1,
                "custom": [{"fieldId": 42, "value": None}],
            }
        )
        result = json.loads(serialize(model, custom_field_defs=self.DEFS))
        assert "customFields" not in result

    def test_excluded_without_defs(self):
        """Raw custom data is excluded when no definitions are provided."""
        model = MockModel(
            {
                "id": 1,
                "custom": [{"fieldId": 42, "value": "test"}],
            }
        )
        result = json.loads(serialize(model))
        assert "custom" not in result
        assert "customFields" not in result

    def test_field_selection_with_custom_fields(self):
        model = MockModel(
            {
                "id": 1,
                "name": "Acme",
                "custom": [{"fieldId": 11, "value": "SaaS"}],
            }
        )
        result = json.loads(
            serialize(model, fields=["name", "customFields"], custom_field_defs=self.DEFS)
        )
        assert result["name"] == "Acme"
        assert "customFields" in result
        assert result["customFields"]["Industry"]["value"] == "SaaS"

    def test_field_selection_custom_alias(self):
        """'custom' in fields list is treated as 'customFields'."""
        model = MockModel(
            {
                "id": 1,
                "custom": [{"fieldId": 11, "value": "SaaS"}],
            }
        )
        result = json.loads(serialize(model, fields=["custom"], custom_field_defs=self.DEFS))
        assert "customFields" in result

    def test_field_selection_excludes_custom_when_not_requested(self):
        model = MockModel(
            {
                "id": 1,
                "name": "Acme",
                "custom": [{"fieldId": 11, "value": "SaaS"}],
            }
        )
        result = json.loads(serialize(model, fields=["name"], custom_field_defs=self.DEFS))
        assert "customFields" not in result
