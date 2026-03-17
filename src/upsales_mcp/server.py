"""Upsales CRM MCP Server.

Exposes Upsales CRM objects (contacts, companies, appointments, phone calls, orders, mail,
activities, agreements, products, users) as MCP tools for get and find operations.

Supports two modes:
- Local (stdio): API key from UPSALES_API_KEY env var
- Hosted (streamable-http): Each client sends their API key as Bearer token
"""

import contextvars
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


def _build_instructions() -> str:
    """Build MCP instructions, optionally including current user context."""
    base = (
        "Upsales CRM server providing read access to contacts, companies, "
        "appointments (meetings), phone calls, orders, emails, activities (tasks), "
        "agreements (subscriptions), products, and users. "
        "Use find tools with filter operators like >=, <=, !=, *value for contains. "
        "All date filters use ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS). "
        "IMPORTANT: Always use the 'fields' parameter to request only the fields you need. "
        "This dramatically reduces response size. Example: fields=['id', 'name', 'phone']."
    )
    user_id = os.environ.get("UPSALES_USER_ID")
    if user_id:
        base += (
            f" The current user's Upsales user ID is {user_id}."
            " When the user says 'my' or 'mine' (e.g. 'my meetings', 'my orders'),"
            f" always filter by user.id={user_id}."
        )
    return base


mcp = FastMCP(
    "Upsales CRM",
    stateless_http=True if _is_hosted() else False,
    json_response=True if _is_hosted() else False,
    host="0.0.0.0" if _is_hosted() else "127.0.0.1",
    port=int(os.environ.get("PORT", 8000)),
    instructions=_build_instructions(),
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
    # Import tools to register them on the mcp instance
    import upsales_mcp.tools  # noqa: F401

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
