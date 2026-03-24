"""Upsales CRM MCP tool definitions.

All get/find tools for each entity are registered here on the shared `mcp` instance.
"""

import functools
import json

from upsales_mcp import cache
from upsales_mcp.filters import map_order_fields, transform_filters
from upsales_mcp.serialize import serialize
from upsales_mcp.server import mcp, _get_api_key, _get_client, _get_user_id


# ---------------------------------------------------------------------------
# Error handling decorator
# ---------------------------------------------------------------------------


def handle_errors(func):
    """Wrap a tool function to catch exceptions and return structured JSON errors."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            error_type = type(exc).__name__
            return json.dumps({"error": str(exc), "type": error_type})

    return wrapper


# ---------------------------------------------------------------------------
# Pagination metadata helper
# ---------------------------------------------------------------------------


def _build_metadata(total: int, count: int, offset: int, limit: int) -> dict:
    """Build response metadata with pagination hints."""
    meta = {"total": total, "count": count}
    remaining = total - (offset + count)
    if remaining > 0:
        meta["hasMore"] = True
        meta["nextOffset"] = offset + count
        meta["remaining"] = remaining
    return meta


# ---------------------------------------------------------------------------
# Custom field definitions helper
# ---------------------------------------------------------------------------

# Map internal entity keys to custom fields API entity names
_CUSTOM_FIELD_ENTITIES = {
    "companies": "account",
    "contacts": "contact",
    "appointments": "appointment",
    "activities": "activity",
    "agreements": "agreement",
    "orders": "order",
    "products": "product",
    "users": "user",
}


async def _get_custom_defs(entity_key: str) -> dict[int, dict] | None:
    """Fetch and cache custom field definitions for an entity.

    Returns dict mapping fieldId -> {"name": str, "type": str, "alias": str|None},
    or None if the entity doesn't support custom fields.
    """
    api_entity = _CUSTOM_FIELD_ENTITIES.get(entity_key)
    if not api_entity:
        return None

    api_key = _get_api_key()
    cache_key = cache.make_key("custom_defs", api_key, api_entity)
    cached_val = cache.get(cache_key)
    if cached_val:
        return json.loads(cached_val)

    async with _get_client() as client:
        fields = await client.custom_fields.list_for_entity(api_entity)

    defs = {}
    for f in fields:
        defs[f.id] = {"name": f.name, "type": f.datatype, "alias": f.alias}
    cache.put(cache_key, json.dumps(defs))
    return defs


def _map_custom_fields_for_api(fields: list[str] | None) -> list[str] | None:
    """Map 'customFields' virtual field to 'custom' for the API f[] parameter."""
    if not fields:
        return fields
    return ["custom" if f == "customFields" else f for f in fields]


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------


@mcp.tool()
@handle_errors
async def get_company(company_id: int) -> str:
    """Get a single company (account) by ID.

    Includes resolved custom fields (customFields) showing field name, value, fieldId, and type.

    Args:
        company_id: The Upsales company/account ID.
    """
    custom_defs = await _get_custom_defs("companies")
    async with _get_client() as client:
        result = await client.companies.get(company_id)
    return serialize(result, custom_field_defs=custom_defs)


@mcp.tool()
@handle_errors
async def find_companies(
    filters: dict[str, str | int | list[str]] | None = None,
    sort: str | None = None,
    limit: int = 50,
    offset: int = 0,
    fields: list[str] | None = None,
) -> str:
    """Find companies with optional filters and pagination.

    Filter operators:
        field: value         - Equals
        field: ">=value"     - Greater than or equals
        field: ">value"      - Greater than
        field: "<=value"     - Less than or equals
        field: "<value"      - Less than
        field: "!=value"     - Not equals
        field: "*value"      - Contains (substring search)

    For range queries on the same field, use a list of values:
        field: [">=value1", "<=value2"]

    Common filter fields: name, phone, webpage, regDate, modDate, active,
    turnover, noEmployees, journeyStep

    Custom field filters: Use custom.FIELD_ID to filter by custom field values.
        First use find_custom_fields("company") to discover available fields and their IDs.
        Example: {"custom.42": "2026-03-14"} or {"custom.42": ">=2026-04-14"}

    Args:
        filters: Optional dict of field-value pairs with operators.
            Values can be a list for range queries on the same field.
        sort: Sort field. Prefix with '-' for descending (e.g. '-regDate').
        limit: Max results (default 50, max 1000).
        offset: Pagination offset.
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'name', 'phone']
            Use 'customFields' to include resolved custom field values.
            Common fields: id, name, phone, webpage, orgNo, active, addresses,
            users, regDate, modDate, journeyStep, turnover, noEmployees, customFields

    Example filters:
        {"name": "*Acme", "active": 1} - Active companies containing "Acme"
        {"regDate": [">=2024-01-01", "<=2024-12-31"]} - Companies created in 2024
        {"turnover": ">=5000000"} - Companies with revenue above 5M
        {"custom.42": ">=2026-04-14"} - Custom field 42 on or after date
    """
    custom_defs = await _get_custom_defs("companies")
    api_filters = transform_filters(filters) if filters else {}
    api_fields = _map_custom_fields_for_api(fields)
    async with _get_client() as client:
        result, meta = await client.companies._list_with_metadata(
            limit=limit, offset=offset, sort=sort, fields=api_fields, **api_filters
        )
    total = meta.get("total", len(result))
    return serialize(
        result,
        fields,
        metadata=_build_metadata(total, len(result), offset, limit),
        custom_field_defs=custom_defs,
    )


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------


@mcp.tool()
@handle_errors
async def get_contact(contact_id: int) -> str:
    """Get a single contact by ID.

    Includes resolved custom fields (customFields) showing field name, value, fieldId, and type.

    Args:
        contact_id: The Upsales contact ID.
    """
    custom_defs = await _get_custom_defs("contacts")
    async with _get_client() as client:
        result = await client.contacts.get(contact_id)
    return serialize(result, custom_field_defs=custom_defs)


@mcp.tool()
@handle_errors
async def find_contacts(
    filters: dict[str, str | int | list[str]] | None = None,
    sort: str | None = None,
    limit: int = 50,
    offset: int = 0,
    fields: list[str] | None = None,
) -> str:
    """Find contacts with optional filters and pagination.

    Common filter fields: name, email, phone, title, client.id (company ID),
    regDate, modDate, active, journeyStep

    Custom field filters: Use custom.FIELD_ID to filter by custom field values.
        First use find_custom_fields("contact") to discover available fields and their IDs.

    Args:
        filters: Optional dict of field-value pairs with operators.
        sort: Sort field. Prefix with '-' for descending.
        limit: Max results (default 50, max 1000).
        offset: Pagination offset.
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'name', 'email', 'phone', 'title']
            Use 'customFields' to include resolved custom field values.
            Common fields: id, name, email, phone, cellPhone, title, client,
            regDate, modDate, active, journeyStep, customFields

    Example filters:
        {"name": "*John", "active": 1} - Active contacts named John
        {"client.id": 123} - All contacts at company 123
        {"email": "*@acme.com"} - Contacts with acme.com email
    """
    custom_defs = await _get_custom_defs("contacts")
    api_filters = transform_filters(filters) if filters else {}
    api_fields = _map_custom_fields_for_api(fields)
    async with _get_client() as client:
        result, meta = await client.contacts._list_with_metadata(
            limit=limit, offset=offset, sort=sort, fields=api_fields, **api_filters
        )
    total = meta.get("total", len(result))
    return serialize(
        result,
        fields,
        metadata=_build_metadata(total, len(result), offset, limit),
        custom_field_defs=custom_defs,
    )


# ---------------------------------------------------------------------------
# Appointments (Meetings)
# ---------------------------------------------------------------------------


@mcp.tool()
@handle_errors
async def get_appointment(appointment_id: int) -> str:
    """Get a single appointment/meeting by ID.

    Includes resolved custom fields (customFields) showing field name, value, fieldId, and type.

    Args:
        appointment_id: The Upsales appointment ID.
    """
    custom_defs = await _get_custom_defs("appointments")
    async with _get_client() as client:
        result = await client.appointments.get(appointment_id)
    return serialize(result, custom_field_defs=custom_defs)


@mcp.tool()
@handle_errors
async def find_appointments(
    filters: dict[str, str | int | list[str]] | None = None,
    sort: str | None = None,
    limit: int = 50,
    offset: int = 0,
    fields: list[str] | None = None,
) -> str:
    """Find appointments/meetings with optional filters and pagination.

    Common filter fields: description, date, endDate, outcome (planned/completed/notCompleted),
    client.id (company ID), user.id, activityType.id, location

    Args:
        filters: Optional dict of field-value pairs with operators.
        sort: Sort field. Prefix with '-' for descending (e.g. '-date').
        limit: Max results (default 50, max 1000).
        offset: Pagination offset.
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'description', 'date', 'endDate', 'outcome']
            Common fields: id, description, date, endDate, outcome, location,
            client, contact, users, activityType, regDate

    Custom field filters: Use custom.FIELD_ID to filter by custom field values.
        First use find_custom_fields("appointment") to discover available fields and their IDs.

    Example filters:
        {"date": [">=2025-03-16", "<=2025-03-22"]} - Appointments in a specific week
        {"outcome": "planned"} - Only planned meetings
        {"client.id": 123} - Meetings for a specific company
    """
    custom_defs = await _get_custom_defs("appointments")
    api_filters = transform_filters(filters) if filters else {}
    api_fields = _map_custom_fields_for_api(fields)
    async with _get_client() as client:
        result, meta = await client.appointments._list_with_metadata(
            limit=limit, offset=offset, sort=sort, fields=api_fields, **api_filters
        )
    total = meta.get("total", len(result))
    return serialize(
        result,
        fields,
        metadata=_build_metadata(total, len(result), offset, limit),
        custom_field_defs=custom_defs,
    )


# ---------------------------------------------------------------------------
# Phone Calls
# ---------------------------------------------------------------------------


@mcp.tool()
@handle_errors
async def get_phone_call(phone_call_id: int) -> str:
    """Get a single phone call by ID.

    Args:
        phone_call_id: The Upsales phone call ID.
    """
    async with _get_client() as client:
        result = await client.phone_calls.get(phone_call_id)
    return serialize(result)


@mcp.tool()
@handle_errors
async def find_phone_calls(
    filters: dict[str, str | int | list[str]] | None = None,
    sort: str | None = None,
    limit: int = 50,
    offset: int = 0,
    fields: list[str] | None = None,
) -> str:
    """Find phone calls with optional filters and pagination.

    Common filter fields: user.id, client.id (company ID), contact.id,
    regDate, type, duration

    Args:
        filters: Optional dict of field-value pairs with operators.
        sort: Sort field. Prefix with '-' for descending.
        limit: Max results (default 50, max 1000).
        offset: Pagination offset.
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'date', 'duration', 'client', 'contact']
            Common fields: id, date, duration, client, contact, user,
            type, regDate

    Example filters:
        {"user.id": 5} - Calls by a specific user
        {"client.id": 123} - Calls for a specific company
    """
    api_filters = transform_filters(filters) if filters else {}
    async with _get_client() as client:
        result, meta = await client.phone_calls._list_with_metadata(
            limit=limit, offset=offset, sort=sort, fields=fields, **api_filters
        )
    total = meta.get("total", len(result))
    return serialize(result, fields, metadata=_build_metadata(total, len(result), offset, limit))


# ---------------------------------------------------------------------------
# Activities (Tasks)
# ---------------------------------------------------------------------------


@mcp.tool()
@handle_errors
async def get_activity(activity_id: int) -> str:
    """Get a single activity/task by ID.

    Includes resolved custom fields (customFields) showing field name, value, fieldId, and type.

    Args:
        activity_id: The Upsales activity ID.
    """
    custom_defs = await _get_custom_defs("activities")
    async with _get_client() as client:
        result = await client.activities.get(activity_id)
    return serialize(result, custom_field_defs=custom_defs)


@mcp.tool()
@handle_errors
async def find_activities(
    filters: dict[str, str | int | list[str]] | None = None,
    sort: str | None = None,
    limit: int = 50,
    offset: int = 0,
    fields: list[str] | None = None,
) -> str:
    """Find activities/tasks with optional filters and pagination.

    Common filter fields: description, date, priority, user.id, client.id (company ID),
    contact.id, isAppointment (0=task, 1=appointment), regDate, modDate

    Args:
        filters: Optional dict of field-value pairs with operators.
        sort: Sort field. Prefix with '-' for descending (e.g. '-date').
        limit: Max results (default 50, max 1000).
        offset: Pagination offset.
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'description', 'date', 'priority', 'users', 'client']
            Common fields: id, description, date, notes, priority, users,
            client, contact, regDate, modDate

    Custom field filters: Use custom.FIELD_ID to filter by custom field values.
        First use find_custom_fields("activity") to discover available fields and their IDs.

    Example filters:
        {"user.id": 5} - Activities for a specific user
        {"priority": ">=3"} - High priority activities
        {"date": [">=2025-01-01", "<=2025-01-31"]} - Activities in January
    """
    custom_defs = await _get_custom_defs("activities")
    api_filters = transform_filters(filters) if filters else {}
    api_fields = _map_custom_fields_for_api(fields)
    async with _get_client() as client:
        result, meta = await client.activities._list_with_metadata(
            limit=limit, offset=offset, sort=sort, fields=api_fields, **api_filters
        )
    total = meta.get("total", len(result))
    return serialize(
        result,
        fields,
        metadata=_build_metadata(total, len(result), offset, limit),
        custom_field_defs=custom_defs,
    )


# ---------------------------------------------------------------------------
# Agreements (Subscriptions/Contracts)
# ---------------------------------------------------------------------------


@mcp.tool()
@handle_errors
async def get_agreement(agreement_id: int) -> str:
    """Get a single agreement/subscription by ID.

    Includes resolved custom fields (customFields) showing field name, value, fieldId, and type.

    Args:
        agreement_id: The Upsales agreement ID.
    """
    custom_defs = await _get_custom_defs("agreements")
    async with _get_client() as client:
        result = await client.agreements.get(agreement_id)
    return serialize(result, custom_field_defs=custom_defs)


@mcp.tool()
@handle_errors
async def find_agreements(
    filters: dict[str, str | int | list[str]] | None = None,
    sort: str | None = None,
    limit: int = 50,
    offset: int = 0,
    fields: list[str] | None = None,
) -> str:
    """Find agreements/subscriptions with optional filters and pagination.

    Common filter fields: description, client.id (company ID), user.id,
    stage.id, value, currency, regDate, modDate

    Args:
        filters: Optional dict of field-value pairs with operators.
        sort: Sort field. Prefix with '-' for descending.
        limit: Max results (default 50, max 1000).
        offset: Pagination offset.
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'description', 'value', 'client', 'stage']
            Common fields: id, description, value, yearlyValue, currency,
            client, contact, user, stage, metadata, regDate, modDate

    Custom field filters: Use custom.FIELD_ID to filter by custom field values.
        First use find_custom_fields("agreement") to discover available fields and their IDs.

    Example filters:
        {"client.id": 123} - Agreements for a specific company
        {"value": ">=10000"} - High-value agreements
    """
    custom_defs = await _get_custom_defs("agreements")
    api_filters = transform_filters(filters) if filters else {}
    # WORKAROUND: Upsales API bug (WEB-5367) — the agreement mapper unconditionally
    # sub-maps obj.metadata, crashing if metadata is missing from the ES _source.
    # Always include 'metadata' in f[] to prevent the 500 error.
    api_fields = _map_custom_fields_for_api(fields)
    api_fields = list(api_fields) + ["metadata"] if api_fields else api_fields
    async with _get_client() as client:
        result, meta = await client.agreements._list_with_metadata(
            limit=limit, offset=offset, sort=sort, fields=api_fields, **api_filters
        )
    total = meta.get("total", len(result))
    return serialize(
        result,
        fields,
        metadata=_build_metadata(total, len(result), offset, limit),
        custom_field_defs=custom_defs,
    )


# ---------------------------------------------------------------------------
# Products (cached — products rarely change)
# ---------------------------------------------------------------------------


@mcp.tool()
@handle_errors
async def get_product(product_id: int) -> str:
    """Get a single product by ID. Results are cached for 5 minutes.

    Includes resolved custom fields (customFields) showing field name, value, fieldId, and type.

    Args:
        product_id: The Upsales product ID.
    """
    api_key = _get_api_key()
    cache_key = cache.make_key("get_product", api_key, product_id)
    cached_val = cache.get(cache_key)
    if cached_val:
        return cached_val

    custom_defs = await _get_custom_defs("products")
    async with _get_client() as client:
        result = await client.products.get(product_id)
    value = serialize(result, custom_field_defs=custom_defs)
    cache.put(cache_key, value)
    return value


@mcp.tool()
@handle_errors
async def find_products(
    filters: dict[str, str | int | list[str]] | None = None,
    sort: str | None = None,
    limit: int = 50,
    offset: int = 0,
    fields: list[str] | None = None,
) -> str:
    """Find products with optional filters and pagination. Results are cached for 5 minutes.

    Common filter fields: name, active, articleNo, listPrice, isRecurring,
    category.id

    Args:
        filters: Optional dict of field-value pairs with operators.
        sort: Sort field. Prefix with '-' for descending.
        limit: Max results (default 50, max 1000).
        offset: Pagination offset.
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'name', 'listPrice', 'active']
            Common fields: id, name, listPrice, purchaseCost, articleNo,
            active, isRecurring, category, description

    Example filters:
        {"active": 1} - Active products only
        {"name": "*Premium"} - Products containing "Premium"
        {"isRecurring": 1} - Recurring products only
    """
    api_key = _get_api_key()
    cache_key = cache.make_key("find_products", api_key, filters, sort, limit, offset, fields)
    cached_val = cache.get(cache_key)
    if cached_val:
        return cached_val

    custom_defs = await _get_custom_defs("products")
    api_filters = transform_filters(filters) if filters else {}
    api_fields = _map_custom_fields_for_api(fields)
    async with _get_client() as client:
        result, meta = await client.products._list_with_metadata(
            limit=limit, offset=offset, sort=sort, fields=api_fields, **api_filters
        )
    total = meta.get("total", len(result))
    value = serialize(
        result,
        fields,
        metadata=_build_metadata(total, len(result), offset, limit),
        custom_field_defs=custom_defs,
    )
    cache.put(cache_key, value)
    return value


# ---------------------------------------------------------------------------
# Users (cached — users rarely change)
# ---------------------------------------------------------------------------


@mcp.tool()
@handle_errors
async def get_me() -> str:
    """Get the current user's Upsales profile.

    Returns the user profile for the configured UPSALES_USER_ID.
    Use this to find out who the current user is and their Upsales user ID.

    Returns an error if UPSALES_USER_ID is not configured.
    """
    user_id = _get_user_id()
    if not user_id:
        return '{"error": "UPSALES_USER_ID not configured. Send X-Upsales-User-Id header (hosted) or set UPSALES_USER_ID env var (local).", "type": "ConfigError"}'

    api_key = _get_api_key()
    cache_key = cache.make_key("get_me", api_key, user_id)
    cached = cache.get(cache_key)
    if cached:
        return cached

    async with _get_client() as client:
        result = await client.users.get(int(user_id))
    value = serialize(result)
    cache.put(cache_key, value)
    return value


@mcp.tool()
@handle_errors
async def get_user(user_id: int) -> str:
    """Get a single CRM user by ID. Results are cached for 5 minutes.

    Args:
        user_id: The Upsales user ID.
    """
    api_key = _get_api_key()
    cache_key = cache.make_key("get_user", api_key, user_id)
    cached = cache.get(cache_key)
    if cached:
        return cached

    async with _get_client() as client:
        result = await client.users.get(user_id)
    value = serialize(result)
    cache.put(cache_key, value)
    return value


@mcp.tool()
@handle_errors
async def find_users(
    filters: dict[str, str | int | list[str]] | None = None,
    sort: str | None = None,
    limit: int = 50,
    offset: int = 0,
    fields: list[str] | None = None,
) -> str:
    """Find CRM users with optional filters and pagination. Results are cached for 5 minutes.

    Common filter fields: name, email, active, administrator, role.id

    Args:
        filters: Optional dict of field-value pairs with operators.
        sort: Sort field. Prefix with '-' for descending.
        limit: Max results (default 50, max 1000).
        offset: Pagination offset.
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'name', 'email', 'active']
            Common fields: id, name, email, active, role, administrator,
            userPhone, userTitle, regDate

    Example filters:
        {"active": 1} - Active users only
        {"administrator": 1} - Admin users
        {"name": "*John"} - Users named John
    """
    api_key = _get_api_key()
    cache_key = cache.make_key("find_users", api_key, filters, sort, limit, offset, fields)
    cached = cache.get(cache_key)
    if cached:
        return cached

    api_filters = transform_filters(filters) if filters else {}
    async with _get_client() as client:
        result, meta = await client.users._list_with_metadata(
            limit=limit, offset=offset, sort=sort, fields=fields, **api_filters
        )
    total = meta.get("total", len(result))
    value = serialize(result, fields, metadata=_build_metadata(total, len(result), offset, limit))
    cache.put(cache_key, value)
    return value


# ---------------------------------------------------------------------------
# Mail
# ---------------------------------------------------------------------------


@mcp.tool()
@handle_errors
async def get_mail(mail_id: int) -> str:
    """Get a single email by ID.

    Note: The 'body' field (full HTML) is excluded by default to save context.

    Args:
        mail_id: The Upsales mail ID.
    """
    async with _get_client() as client:
        result = await client.mail.get(mail_id)
    return serialize(result)


@mcp.tool()
@handle_errors
async def find_mail(
    filters: dict[str, str | int | list[str]] | None = None,
    sort: str | None = None,
    limit: int = 50,
    offset: int = 0,
    fields: list[str] | None = None,
) -> str:
    """Find emails with optional filters and pagination.

    Note: The 'body' field (full HTML) is excluded by default to save context.
    Request it explicitly via fields=['body'] if needed.

    Common filter fields: type (out/in/pro/err), subject, date, client.id (company ID),
    contact.id, user.id, mailThreadId

    Args:
        filters: Optional dict of field-value pairs with operators.
        sort: Sort field. Prefix with '-' for descending (e.g. '-date').
        limit: Max results (default 50, max 1000).
        offset: Pagination offset.
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'subject', 'date', 'type', 'to', 'from']
            Common fields: id, subject, date, type, to, from, fromName,
            client, contact, users, body

    Example filters:
        {"type": "out"} - Sent emails only
        {"client.id": 123} - Emails for a specific company
        {"date": [">=2025-01-01", "<=2025-01-31"]} - Emails in January 2025
    """
    api_filters = transform_filters(filters) if filters else {}
    async with _get_client() as client:
        result, meta = await client.mail._list_with_metadata(
            limit=limit, offset=offset, sort=sort, fields=fields, **api_filters
        )
    total = meta.get("total", len(result))
    return serialize(result, fields, metadata=_build_metadata(total, len(result), offset, limit))


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


@mcp.tool()
@handle_errors
async def get_order(order_id: int) -> str:
    """Get a single order by ID.

    Includes resolved custom fields (customFields) showing field name, value, fieldId, and type.

    Args:
        order_id: The Upsales order ID.
    """
    custom_defs = await _get_custom_defs("orders")
    async with _get_client() as client:
        result = await client.orders.get(order_id)
    return serialize(result, custom_field_defs=custom_defs)


@mcp.tool()
@handle_errors
async def find_orders(
    filters: dict[str, str | int | list[str]] | None = None,
    sort: str | None = None,
    limit: int = 50,
    offset: int = 0,
    fields: list[str] | None = None,
) -> str:
    """Find orders with optional filters and pagination.

    Common filter fields: description, date, client.id (company ID), user.id,
    stage.id, probability, value, currency, regDate, modDate

    Args:
        filters: Optional dict of field-value pairs with operators.
        sort: Sort field. Prefix with '-' for descending (e.g. '-date').
        limit: Max results (default 50, max 1000).
        offset: Pagination offset.
        fields: List of field names to return. Reduces response size significantly.
            Supports dot-notation for nested fields (e.g. 'orderRow.product.id').
            Example: ['id', 'description', 'date', 'value', 'probability']
            Common fields: id, description, date, value, probability, currency,
            client, contact, user, stage, orderRow, regDate, modDate
            Nested orderRow fields: orderRow.product.id, orderRow.product.name,
            orderRow.price, orderRow.quantity, orderRow.discount

    Custom field filters: Use custom.FIELD_ID to filter by custom field values.
        First use find_custom_fields("order") to discover available fields and their IDs.

    Example filters:
        {"stage.id": 5} - Orders at a specific stage
        {"date": ">=2024-01-01"} - Orders since 2024
        {"client.id": 123, "probability": ">=50"} - Likely orders for a company
        {"custom.42": "2026-03-14"} - Orders with custom field 42 = specific date

    Tip: For analytics (e.g. best-selling products), use sparse nested fields:
        fields=['id', 'orderRow.product.id', 'orderRow.product.name',
                'orderRow.price', 'orderRow.quantity']
    """
    custom_defs = await _get_custom_defs("orders")
    api_filters = transform_filters(filters) if filters else {}
    api_fields = _map_custom_fields_for_api(fields)
    api_fields = map_order_fields(api_fields)
    async with _get_client() as client:
        result, meta = await client.orders._list_with_metadata(
            limit=limit, offset=offset, sort=sort, fields=api_fields, **api_filters
        )
    total = meta.get("total", len(result))
    return serialize(
        result,
        fields,
        metadata=_build_metadata(total, len(result), offset, limit),
        custom_field_defs=custom_defs,
    )


# ---------------------------------------------------------------------------
# Custom Fields (definitions — cached, rarely change)
# ---------------------------------------------------------------------------

# Map user-facing entity names to Upsales API entity names
_ENTITY_ALIASES = {
    "company": "account",
    "companies": "account",
    "account": "account",
    "order": "order",
    "orders": "order",
    "orderrow": "orderrow",
    "agreement": "agreement",
    "agreements": "agreement",
    "activity": "activity",
    "activities": "activity",
    "appointment": "appointment",
    "appointments": "appointment",
    "contact": "contact",
    "contacts": "contact",
    "product": "product",
    "products": "product",
    "user": "user",
    "users": "user",
}

_VALID_ENTITIES = sorted(set(_ENTITY_ALIASES.values()))


@mcp.tool()
@handle_errors
async def find_custom_fields(entity: str) -> str:
    """List all custom field definitions for an entity. Results are cached for 5 minutes.

    Custom fields are user-defined fields on Upsales entities. This tool returns
    the field definitions (name, type, alias, options) — not the field values on
    individual records. Use this to understand what custom fields exist before
    querying entity data.

    Args:
        entity: Entity type. Accepted values: account (or company/companies),
            order, orderrow, agreement, activity, appointment, contact,
            product, user.

    Returns:
        JSON array of custom field definitions with id, name, datatype, alias, etc.
        For Select/MultiSelect fields, 'default' contains the available options.
    """
    api_entity = _ENTITY_ALIASES.get(entity.lower())
    if not api_entity:
        return json.dumps(
            {
                "error": f"Unknown entity '{entity}'",
                "type": "ValueError",
                "validEntities": _VALID_ENTITIES,
            }
        )

    api_key = _get_api_key()
    cache_key = cache.make_key("find_custom_fields", api_key, api_entity)
    cached = cache.get(cache_key)
    if cached:
        return cached

    async with _get_client() as client:
        result = await client.custom_fields.list_for_entity(api_entity)
    value = serialize(result)
    cache.put(cache_key, value)
    return value
