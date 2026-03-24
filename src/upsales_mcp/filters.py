"""Filter transformation utilities for Upsales API queries."""

import json

# Operator mapping: MCP filter syntax → Upsales API syntax
_OPERATOR_MAP = {
    ">=": "gte:",
    "<=": "lte:",
    "!=": "ne:",
    ">": "gt:",
    "<": "lt:",
    "=": "eq:",
    "*": "src:",
}


def parse_op(value: str) -> tuple[str, str]:
    """Parse a filter value into (comparator, raw_value) for the Upsales q[] syntax."""
    for op, api_op in _OPERATOR_MAP.items():
        if value.startswith(op):
            return api_op.rstrip(":"), value[len(op) :]
    return "eq", value


def transform_filters(
    filters: dict[str, str | int | list[str]],
) -> dict[str, str | int]:
    """Transform MCP filter operators to Upsales API syntax.

    Supports list values for range queries on the same field:
        {"date": [">=2026-03-16", "<=2026-03-22"]}
    These are converted to q[] JSON filters.
    """
    simple: dict[str, str | int] = {}
    # Store parsed (comp, raw) pairs alongside simple filters so we don't
    # re-parse already-transformed values when merging into q[].
    simple_parsed: dict[str, tuple[str, str | int]] = {}
    q_conditions: list[dict] = []
    # Custom field filters: custom.FIELD_ID → Upsales "custom" shortcut param
    custom_conditions: list[str] = []

    for field, value in filters.items():
        # Handle custom field filters: custom.FIELD_ID
        if field.startswith("custom."):
            field_id = field.split(".", 1)[1]
            if isinstance(value, list):
                for v in value:
                    comp, raw = parse_op(str(v))
                    custom_conditions.append(f"{comp}:{field_id}:{raw}")
            else:
                comp, raw = parse_op(str(value))
                custom_conditions.append(f"{comp}:{field_id}:{raw}")
            continue

        if isinstance(value, list):
            # Multiple conditions on same field → must use q[] syntax
            for v in value:
                comp, raw = parse_op(str(v))
                q_conditions.append({"a": field, "c": comp, "v": raw})
        elif isinstance(value, str):
            comp, raw = parse_op(value)
            simple_parsed[field] = (comp, raw)
            # Build the simple API syntax (e.g. "gte:2024-01-01")
            if comp != "eq":
                simple[field] = f"{comp}:{raw}"
            else:
                simple[field] = raw
        else:
            simple[field] = value
            simple_parsed[field] = ("eq", value)

    if q_conditions:
        # Merge simple filters into q[] using pre-parsed values
        for field, (comp, raw) in simple_parsed.items():
            q_conditions.append({"a": field, "c": comp, "v": raw})
        result: dict = {"q[]": [json.dumps(c) for c in q_conditions]}
    else:
        result = simple

    # Add custom field conditions as the "custom" API parameter
    if len(custom_conditions) == 1:
        result["custom"] = custom_conditions[0]
    elif custom_conditions:
        result["custom"] = custom_conditions

    return result


# WORKAROUND: Upsales API bug (WEB-5366) — f[]=value drops the field from the
# response. The f[] parser resolves 'value' -> 'orderValue' for the ES _source
# query, but the response mapper then can't find it to rename back to 'value'.
# Sending f[]=orderValue bypasses the broken resolution and works correctly.
# Fix is merged (upsales-crm#23460), expected live 2026-03-17. Remove this
# workaround once confirmed.
# https://linear.app/upsales/issue/WEB-5366
_ORDER_FIELD_MAP = {"value": "orderValue"}


def map_order_fields(fields: list[str] | None) -> list[str] | None:
    """Map user-facing order field names to API internal names for f[] param."""
    if not fields:
        return fields
    return [_ORDER_FIELD_MAP.get(f, f) for f in fields]
