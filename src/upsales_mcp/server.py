"""Upsales CRM MCP Server.

Exposes Upsales CRM objects (contacts, companies, appointments, phone calls, orders)
as MCP tools for get, list, and search operations.

Supports two modes:
- Local (stdio): API key from UPSALES_API_KEY env var
- Hosted (streamable-http): Each client sends their API key as Bearer token
"""

import contextvars
import json
import os

from mcp.server.fastmcp import FastMCP

from upsales import Upsales

# Store the Bearer token per-request via contextvar
_current_api_key: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_current_api_key", default=None
)


def _is_hosted() -> bool:
    """Check if running in hosted mode (streamable HTTP)."""
    return os.environ.get("MCP_TRANSPORT", "stdio") == "streamable-http"


mcp = FastMCP(
    "Upsales CRM",
    stateless_http=True if _is_hosted() else False,
    json_response=True if _is_hosted() else False,
    host="0.0.0.0" if _is_hosted() else "127.0.0.1",
    port=int(os.environ.get("PORT", 8000)),
    instructions=(
        "Upsales CRM server providing read access to contacts, companies, "
        "appointments (meetings), phone calls, and orders. "
        "Use search tools with filter operators like >=, <=, !=, *value for contains. "
        "All date filters use ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS). "
        "IMPORTANT: Always use the 'fields' parameter to request only the fields you need. "
        "This dramatically reduces response size. Example: fields=['id', 'name', 'phone']."
    ),
)


def _get_api_key() -> str:
    """Get the Upsales API key from Bearer token (hosted) or env var (local)."""
    if _is_hosted():
        token = _current_api_key.get()
        if token:
            return token
        msg = "No Bearer token provided"
        raise ValueError(msg)

    token = os.environ.get("UPSALES_API_KEY") or os.environ.get("UPSALES_TOKEN")
    if not token:
        msg = "UPSALES_API_KEY environment variable is required"
        raise ValueError(msg)
    return token


def _get_client() -> Upsales:
    """Create an Upsales client from the current user's API key."""
    return Upsales(token=_get_api_key())


def _serialize(obj: object, fields: list[str] | None = None) -> str:
    """Serialize a model or list of models to JSON string.

    Args:
        obj: A Pydantic model or list of models.
        fields: If provided, only include these keys in the output (plus 'id' always).
    """
    # Exclude computed/noise fields that add no value for AI agents
    _exclude = {
        # SDK computed properties
        "custom_fields",
        "is_active",
        "full_name",
        "has_phone",
        "contact_count",
        "is_headquarters",
        "is_appointment",
        "has_outcome",
        "has_weblink",
        "has_attendees",
        "attendee_count",
        "is_locked",
        "expected_value",
        "is_recurring",
        "margin_percentage",
        # Order: weighted values (= base value * probability/100, always computable)
        "weightedValue",
        "weightedOneOffValue",
        "weightedMonthlyValue",
        "weightedAnnualValue",
        "weightedContributionMargin",
        "weightedContributionMarginLocalCurrency",
        "weightedValueInMasterCurrency",
        "weightedOneOffValueInMasterCurrency",
        "weightedMonthlyValueInMasterCurrency",
        "weightedAnnualValueInMasterCurrency",
        # Order: master currency duplicates (= base value when currencyRate=1)
        "valueInMasterCurrency",
        "oneOffValueInMasterCurrency",
        "monthlyValueInMasterCurrency",
        "annualValueInMasterCurrency",
        # Order: noise fields
        "contributionMarginLocalCurrency",
        "risks",
        "salesCoach",
        "checklist",
        "titleCategories",
        "projectPlanOptions",
        "lastIntegrationStatus",
        "userSalesStatistics",
        "periodization",
        # UI permission flags
        "userEditable",
        "userRemovable",
        # Company: internal tracking
        "excludedFromProspectingMonitor",
        "isMonitored",
        "hasVisit",
        "hasMail",
        "hasForm",
        "autoMatchedProspectingId",
        "prospectingId",
        "prospectingUpdateDate",
        "prospectingCreditRating",
        "prospectingNumericCreditRating",
        "monitorChangeDate",
        # Company: low-value nested objects (all zeros/false for most accounts)
        "growth",
        "ads",
        "supportTickets",
        "scoreUpdateDate",
        # Contact: internal tracking
        "isPriority",
        "emailBounceReason",
        "mailBounces",
        "optins",
        "socialEvent",
        "connectedClients",
        # Order: raw custom fields (opaque fieldIds, not useful without metadata)
        "custom",
        # Order: activity counters (rarely useful)
        "noCompletedAppointments",
        "noPostponedAppointments",
        "noTimesCallsNotAnswered",
        "noTimesClosingDateChanged",
        "noTimesOrderValueChanged",
    }

    # Keys to strip from nested objects (e.g. orderRow items)
    _nested_exclude = {
        "valueInMasterCurrency",
        "monthlyValueInMasterCurrency",
        "annualValueInMasterCurrency",
        "contributionMarginLocalCurrency",
        "contributionMargin",
        "bundleFixedPrice",
        "tierQuantity",
        "sortId",
        "bundleRows",
        "custom",
        "productId",
        "purchaseCost",
        "listPrice",
    }

    def _strip_empty(d: dict) -> dict:
        """Recursively strip null/empty values and noise from dicts."""
        cleaned = {}
        for k, v in d.items():
            if v is None or v == [] or v == {} or v == "":
                continue
            if k in _nested_exclude:
                continue
            if isinstance(v, dict):
                v = _strip_empty(v)
                if not v:
                    continue
            elif isinstance(v, list):
                v = [_strip_empty(i) if isinstance(i, dict) else i for i in v]
            cleaned[k] = v
        return cleaned

    def _dump(item: object) -> dict:
        data = item.model_dump(
            mode="json",
            by_alias=True,
            exclude=_exclude,
        )
        if fields:
            keep = {"id"} | set(fields)
            data = {k: v for k, v in data.items() if k in keep}
        # Always clean nested values
        data = _strip_empty(data)
        return data

    if isinstance(obj, list):
        return json.dumps([_dump(item) for item in obj], indent=2, default=str)
    return json.dumps(_dump(obj), indent=2, default=str)


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_company(company_id: int) -> str:
    """Get a single company (account) by ID.

    Args:
        company_id: The Upsales company/account ID.
    """
    async with _get_client() as client:
        result = await client.companies.get(company_id)
    return _serialize(result)


@mcp.tool()
async def list_companies(
    limit: int = 50,
    offset: int = 0,
    sort: str | None = None,
    fields: list[str] | None = None,
) -> str:
    """List companies with pagination.

    Args:
        limit: Max results to return (default 50, max 1000).
        offset: Pagination offset.
        sort: Sort field. Prefix with '-' for descending (e.g. '-regDate').
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'name', 'phone', 'webpage', 'addresses']
            Common fields: id, name, phone, webpage, orgNo, active, addresses,
            users, regDate, modDate, journeyStep, turnover, noEmployees
    """
    async with _get_client() as client:
        result = await client.companies.list(limit=limit, offset=offset, sort=sort, fields=fields)
    return _serialize(result, fields)


@mcp.tool()
async def search_companies(
    filters: dict[str, str | int],
    sort: str | None = None,
    limit: int = 100,
    fields: list[str] | None = None,
) -> str:
    """Search companies using filters with comparison operators.

    Filter operators:
        field: value         - Equals
        field: ">=value"     - Greater than or equals
        field: ">value"      - Greater than
        field: "<=value"     - Less than or equals
        field: "<value"      - Less than
        field: "!=value"     - Not equals
        field: "*value"      - Contains (substring search)

    Common filter fields: name, phone, webpage, regDate, modDate, active

    Args:
        filters: Dict of field-value pairs with optional operators.
        sort: Sort field. Prefix with '-' for descending.
        limit: Max results (default 100).
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'name', 'phone']

    Example filters:
        {"name": "*Acme", "active": 1} - Active companies containing "Acme"
        {"regDate": ">=2024-01-01"} - Companies created since 2024
    """
    async with _get_client() as client:
        result = await client.companies.search(sort=sort, fields=fields, **filters)
    return _serialize(result[:limit], fields)


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_contact(contact_id: int) -> str:
    """Get a single contact by ID.

    Args:
        contact_id: The Upsales contact ID.
    """
    async with _get_client() as client:
        result = await client.contacts.get(contact_id)
    return _serialize(result)


@mcp.tool()
async def list_contacts(
    limit: int = 50,
    offset: int = 0,
    sort: str | None = None,
    fields: list[str] | None = None,
) -> str:
    """List contacts with pagination.

    Args:
        limit: Max results to return (default 50, max 1000).
        offset: Pagination offset.
        sort: Sort field. Prefix with '-' for descending.
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'name', 'email', 'phone', 'title']
            Common fields: id, name, email, phone, cellPhone, title, client,
            regDate, modDate, active, journeyStep
    """
    async with _get_client() as client:
        result = await client.contacts.list(limit=limit, offset=offset, sort=sort, fields=fields)
    return _serialize(result, fields)


@mcp.tool()
async def search_contacts(
    filters: dict[str, str | int],
    sort: str | None = None,
    limit: int = 100,
    fields: list[str] | None = None,
) -> str:
    """Search contacts using filters with comparison operators.

    Common filter fields: name, email, phone, title, client.id (company ID),
    regDate, modDate, active

    Args:
        filters: Dict of field-value pairs with optional operators.
        sort: Sort field. Prefix with '-' for descending.
        limit: Max results (default 100).
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'name', 'email', 'phone']

    Example filters:
        {"name": "*John", "active": 1} - Active contacts named John
        {"client.id": 123} - All contacts at company 123
        {"email": "*@acme.com"} - Contacts with acme.com email
    """
    async with _get_client() as client:
        result = await client.contacts.search(sort=sort, fields=fields, **filters)
    return _serialize(result[:limit], fields)


# ---------------------------------------------------------------------------
# Appointments (Meetings)
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_appointment(appointment_id: int) -> str:
    """Get a single appointment/meeting by ID.

    Args:
        appointment_id: The Upsales appointment ID.
    """
    async with _get_client() as client:
        result = await client.appointments.get(appointment_id)
    return _serialize(result)


@mcp.tool()
async def list_appointments(
    limit: int = 50,
    offset: int = 0,
    sort: str | None = None,
    fields: list[str] | None = None,
) -> str:
    """List appointments/meetings with pagination.

    Args:
        limit: Max results to return (default 50, max 1000).
        offset: Pagination offset.
        sort: Sort field. Prefix with '-' for descending (e.g. '-date').
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'description', 'date', 'endDate', 'outcome']
            Common fields: id, description, date, endDate, outcome, location,
            client, contact, users, activityType, regDate
    """
    async with _get_client() as client:
        result = await client.appointments.list(
            limit=limit, offset=offset, sort=sort, fields=fields
        )
    return _serialize(result, fields)


@mcp.tool()
async def search_appointments(
    filters: dict[str, str | int],
    sort: str | None = None,
    limit: int = 100,
    fields: list[str] | None = None,
) -> str:
    """Search appointments/meetings using filters with comparison operators.

    Common filter fields: description, date, endDate, outcome (planned/completed/notCompleted),
    client.id (company ID), user.id, activityType.id, location

    Args:
        filters: Dict of field-value pairs with optional operators.
        sort: Sort field. Prefix with '-' for descending.
        limit: Max results (default 100).
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'description', 'date', 'outcome']

    Example filters:
        {"date": ">=2024-03-01", "date": "<=2024-03-31"} - Appointments in March
        {"outcome": "planned"} - Only planned meetings
        {"client.id": 123} - Meetings for a specific company
    """
    async with _get_client() as client:
        result = await client.appointments.search(sort=sort, fields=fields, **filters)
    return _serialize(result[:limit], fields)


# ---------------------------------------------------------------------------
# Phone Calls
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_phone_call(phone_call_id: int) -> str:
    """Get a single phone call by ID.

    Args:
        phone_call_id: The Upsales phone call ID.
    """
    async with _get_client() as client:
        result = await client.phone_calls.get(phone_call_id)
    return _serialize(result)


@mcp.tool()
async def list_phone_calls(
    limit: int = 50,
    offset: int = 0,
    sort: str | None = None,
    fields: list[str] | None = None,
) -> str:
    """List phone calls with pagination.

    Args:
        limit: Max results to return (default 50, max 1000).
        offset: Pagination offset.
        sort: Sort field. Prefix with '-' for descending.
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'date', 'duration', 'client', 'contact']
            Common fields: id, date, duration, client, contact, user,
            type, regDate
    """
    async with _get_client() as client:
        result = await client.phone_calls.list(limit=limit, offset=offset, sort=sort, fields=fields)
    return _serialize(result, fields)


@mcp.tool()
async def search_phone_calls(
    filters: dict[str, str | int],
    sort: str | None = None,
    limit: int = 100,
    fields: list[str] | None = None,
) -> str:
    """Search phone calls using filters with comparison operators.

    Common filter fields: user.id, client.id (company ID), contact.id,
    regDate, type, duration

    Args:
        filters: Dict of field-value pairs with optional operators.
        sort: Sort field. Prefix with '-' for descending.
        limit: Max results (default 100).
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'date', 'duration', 'client']

    Example filters:
        {"user.id": 5} - Calls by a specific user
        {"client.id": 123} - Calls for a specific company
    """
    async with _get_client() as client:
        result = await client.phone_calls.search(sort=sort, fields=fields, **filters)
    return _serialize(result[:limit], fields)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

# WORKAROUND: Upsales API bug (WEB-5366) — f[]=value drops the field from the
# response. The f[] parser resolves 'value' -> 'orderValue' for the ES _source
# query, but the response mapper then can't find it to rename back to 'value'.
# Sending f[]=orderValue bypasses the broken resolution and works correctly.
# Fix is merged (upsales-crm#23460), expected live 2026-03-17. Remove this
# workaround once confirmed.
# https://linear.app/upsales/issue/WEB-5366
_ORDER_FIELD_MAP = {"value": "orderValue"}


def _map_order_fields(fields: list[str] | None) -> list[str] | None:
    """Map user-facing order field names to API internal names for f[] param."""
    if not fields:
        return fields
    return [_ORDER_FIELD_MAP.get(f, f) for f in fields]


@mcp.tool()
async def get_order(order_id: int) -> str:
    """Get a single order by ID.

    Args:
        order_id: The Upsales order ID.
    """
    async with _get_client() as client:
        result = await client.orders.get(order_id)
    return _serialize(result)


@mcp.tool()
async def list_orders(
    limit: int = 50,
    offset: int = 0,
    sort: str | None = None,
    fields: list[str] | None = None,
) -> str:
    """List orders with pagination.

    Args:
        limit: Max results to return (default 50, max 1000).
        offset: Pagination offset.
        sort: Sort field. Prefix with '-' for descending (e.g. '-date').
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'description', 'date', 'value', 'probability']
            Common fields: id, description, date, value, probability, currency,
            client, contact, user, stage, orderRow, regDate, modDate
    """
    api_fields = _map_order_fields(fields)
    async with _get_client() as client:
        result = await client.orders.list(limit=limit, offset=offset, sort=sort, fields=api_fields)
    return _serialize(result, fields)


@mcp.tool()
async def search_orders(
    filters: dict[str, str | int],
    sort: str | None = None,
    limit: int = 100,
    fields: list[str] | None = None,
) -> str:
    """Search orders using filters with comparison operators.

    Common filter fields: description, date, client.id (company ID), user.id,
    stage.id, probability, value, currency, regDate, modDate

    Args:
        filters: Dict of field-value pairs with optional operators.
        sort: Sort field. Prefix with '-' for descending.
        limit: Max results (default 100).
        fields: List of field names to return. Reduces response size significantly.
            Example: ['id', 'description', 'date', 'value']

    Example filters:
        {"stage.id": 5} - Orders at a specific stage
        {"date": ">=2024-01-01"} - Orders since 2024
        {"client.id": 123, "probability": ">=50"} - Likely orders for a company
    """
    api_fields = _map_order_fields(fields)
    async with _get_client() as client:
        result = await client.orders.search(sort=sort, fields=api_fields, **filters)
    return _serialize(result[:limit], fields)


def _build_app():
    """Build ASGI app with auth middleware for hosted mode."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    class BearerAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
                if token:
                    _current_api_key.set(token)
                    return await call_next(request)
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Authorization header"},
            )

    asgi_app = mcp.streamable_http_app()
    asgi_app.add_middleware(BearerAuthMiddleware)
    return asgi_app


def main():
    """Run the MCP server in the appropriate transport mode."""
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        import uvicorn

        app = _build_app()
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=int(os.environ.get("PORT", 8000)),
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main()
