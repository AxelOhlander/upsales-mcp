"""Upsales CRM MCP Server.

Exposes Upsales CRM objects (contacts, companies, appointments, phone calls, orders)
as MCP tools for get, list, and search operations.

Supports two modes:
- Local (stdio): API key from UPSALES_API_KEY env var
- Hosted (streamable-http): Each client sends their API key as Bearer token
"""

import json
import os
import sys

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl

from upsales import Upsales


def _is_hosted() -> bool:
    """Check if running in hosted mode (streamable HTTP)."""
    return os.environ.get("MCP_TRANSPORT", "stdio") == "streamable-http"


def _create_server() -> FastMCP:
    """Create the FastMCP server with appropriate auth config."""
    if _is_hosted():
        port = int(os.environ.get("PORT", 8000))
        return FastMCP(
            "Upsales CRM",
            host="0.0.0.0",
            port=port,
            stateless_http=True,
            json_response=True,
            instructions=(
                "Upsales CRM server providing read access to contacts, companies, "
                "appointments (meetings), phone calls, and orders. "
                "Use search tools with filter operators like >=, <=, !=, *value for contains. "
                "All date filters use ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)."
            ),
            token_verifier=UpsalesTokenVerifier(),
            auth=AuthSettings(
                issuer_url=AnyHttpUrl(
                    os.environ.get("AUTH_ISSUER_URL", "https://upsales-mcp-production.up.railway.app")
                ),
                resource_server_url=AnyHttpUrl(
                    os.environ.get("AUTH_RESOURCE_URL", "https://upsales-mcp-production.up.railway.app")
                ),
                required_scopes=[],
            ),
        )
    return FastMCP(
        "Upsales CRM",
        instructions=(
            "Upsales CRM server providing read access to contacts, companies, "
            "appointments (meetings), phone calls, and orders. "
            "Use search tools with filter operators like >=, <=, !=, *value for contains. "
            "All date filters use ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)."
        ),
    )


class UpsalesTokenVerifier(TokenVerifier):
    """Verify Bearer tokens by treating them as Upsales API keys.

    Any non-empty token is accepted. The Upsales API itself will reject
    invalid tokens with a 401, so we don't need to pre-validate.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token or not token.strip():
            return None
        return AccessToken(
            token=token,
            client_id="upsales-user",
            scopes=[],
        )


mcp = _create_server()


def _get_api_key() -> str:
    """Get the Upsales API key from Bearer token (hosted) or env var (local)."""
    if _is_hosted():
        access_token = get_access_token()
        if access_token:
            return access_token.token
        msg = "No Bearer token provided. Send your Upsales API key as: Authorization: Bearer <key>"
        raise ValueError(msg)

    token = os.environ.get("UPSALES_API_KEY") or os.environ.get("UPSALES_TOKEN")
    if not token:
        msg = "UPSALES_API_KEY environment variable is required"
        raise ValueError(msg)
    return token


def _get_client() -> Upsales:
    """Create an Upsales client from the current user's API key."""
    return Upsales(token=_get_api_key())


def _serialize(obj: object) -> str:
    """Serialize a model or list of models to JSON string."""
    if isinstance(obj, list):
        return json.dumps(
            [item.model_dump(mode="json", by_alias=True) for item in obj],
            indent=2,
            default=str,
        )
    return json.dumps(
        obj.model_dump(mode="json", by_alias=True),
        indent=2,
        default=str,
    )


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
) -> str:
    """List companies with pagination.

    Args:
        limit: Max results to return (default 50, max 1000).
        offset: Pagination offset.
        sort: Sort field. Prefix with '-' for descending (e.g. '-regDate').
    """
    async with _get_client() as client:
        result = await client.companies.list(limit=limit, offset=offset, sort=sort)
    return _serialize(result)


@mcp.tool()
async def search_companies(
    filters: dict[str, str | int],
    sort: str | None = None,
    limit: int = 100,
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

    Example filters:
        {"name": "*Acme", "active": 1} - Active companies containing "Acme"
        {"regDate": ">=2024-01-01"} - Companies created since 2024
    """
    async with _get_client() as client:
        result = await client.companies.search(sort=sort, **filters)
    return _serialize(result[:limit])


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
) -> str:
    """List contacts with pagination.

    Args:
        limit: Max results to return (default 50, max 1000).
        offset: Pagination offset.
        sort: Sort field. Prefix with '-' for descending.
    """
    async with _get_client() as client:
        result = await client.contacts.list(limit=limit, offset=offset, sort=sort)
    return _serialize(result)


@mcp.tool()
async def search_contacts(
    filters: dict[str, str | int],
    sort: str | None = None,
    limit: int = 100,
) -> str:
    """Search contacts using filters with comparison operators.

    Common filter fields: name, email, phone, title, client.id (company ID),
    regDate, modDate, active

    Args:
        filters: Dict of field-value pairs with optional operators.
        sort: Sort field. Prefix with '-' for descending.
        limit: Max results (default 100).

    Example filters:
        {"name": "*John", "active": 1} - Active contacts named John
        {"client.id": 123} - All contacts at company 123
        {"email": "*@acme.com"} - Contacts with acme.com email
    """
    async with _get_client() as client:
        result = await client.contacts.search(sort=sort, **filters)
    return _serialize(result[:limit])


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
) -> str:
    """List appointments/meetings with pagination.

    Args:
        limit: Max results to return (default 50, max 1000).
        offset: Pagination offset.
        sort: Sort field. Prefix with '-' for descending (e.g. '-date').
    """
    async with _get_client() as client:
        result = await client.appointments.list(limit=limit, offset=offset, sort=sort)
    return _serialize(result)


@mcp.tool()
async def search_appointments(
    filters: dict[str, str | int],
    sort: str | None = None,
    limit: int = 100,
) -> str:
    """Search appointments/meetings using filters with comparison operators.

    Common filter fields: description, date, endDate, outcome (planned/completed/notCompleted),
    client.id (company ID), user.id, activityType.id, location

    Args:
        filters: Dict of field-value pairs with optional operators.
        sort: Sort field. Prefix with '-' for descending.
        limit: Max results (default 100).

    Example filters:
        {"date": ">=2024-03-01", "date": "<=2024-03-31"} - Appointments in March
        {"outcome": "planned"} - Only planned meetings
        {"client.id": 123} - Meetings for a specific company
    """
    async with _get_client() as client:
        result = await client.appointments.search(sort=sort, **filters)
    return _serialize(result[:limit])


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
) -> str:
    """List phone calls with pagination.

    Args:
        limit: Max results to return (default 50, max 1000).
        offset: Pagination offset.
        sort: Sort field. Prefix with '-' for descending.
    """
    async with _get_client() as client:
        result = await client.phone_calls.list(limit=limit, offset=offset, sort=sort)
    return _serialize(result)


@mcp.tool()
async def search_phone_calls(
    filters: dict[str, str | int],
    sort: str | None = None,
    limit: int = 100,
) -> str:
    """Search phone calls using filters with comparison operators.

    Common filter fields: user.id, client.id (company ID), contact.id,
    regDate, type, duration

    Args:
        filters: Dict of field-value pairs with optional operators.
        sort: Sort field. Prefix with '-' for descending.
        limit: Max results (default 100).

    Example filters:
        {"user.id": 5} - Calls by a specific user
        {"client.id": 123} - Calls for a specific company
    """
    async with _get_client() as client:
        result = await client.phone_calls.search(sort=sort, **filters)
    return _serialize(result[:limit])


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


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
) -> str:
    """List orders with pagination.

    Args:
        limit: Max results to return (default 50, max 1000).
        offset: Pagination offset.
        sort: Sort field. Prefix with '-' for descending (e.g. '-date').
    """
    async with _get_client() as client:
        result = await client.orders.list(limit=limit, offset=offset, sort=sort)
    return _serialize(result)


@mcp.tool()
async def search_orders(
    filters: dict[str, str | int],
    sort: str | None = None,
    limit: int = 100,
) -> str:
    """Search orders using filters with comparison operators.

    Common filter fields: description, date, client.id (company ID), user.id,
    stage.id, probability, value, currency, regDate, modDate

    Args:
        filters: Dict of field-value pairs with optional operators.
        sort: Sort field. Prefix with '-' for descending.
        limit: Max results (default 100).

    Example filters:
        {"stage.id": 5} - Orders at a specific stage
        {"date": ">=2024-01-01"} - Orders since 2024
        {"client.id": 123, "probability": ">=50"} - Likely orders for a company
    """
    async with _get_client() as client:
        result = await client.orders.search(sort=sort, **filters)
    return _serialize(result[:limit])


def main():
    """Run the MCP server in the appropriate transport mode."""
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
