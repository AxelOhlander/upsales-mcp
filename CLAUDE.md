# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MCP server exposing Upsales CRM data as read-only tools. Built with Python 3.13, FastMCP, and the `upsales` Python SDK (private GitHub repo). Two transport modes: local stdio (single user, API key from env) and hosted streamable-http (multi-tenant, Bearer token auth via Starlette middleware).

## Commands

```bash
uv sync                              # Install dependencies
uv run upsales-mcp                   # Run locally (stdio mode, needs UPSALES_API_KEY)
uv run ruff check src/               # Lint
uv run ruff format src/              # Format
MCP_TRANSPORT=streamable-http uv run upsales-mcp  # Run in hosted HTTP mode
```

```bash
uv run pytest tests/ -v               # Run tests
```

## Architecture

Modular layout under `src/upsales_mcp/`:

- **`server.py`** — FastMCP instance (`mcp`), auth (contextvar, Bearer middleware, `_get_client()`), `main()` entrypoint
- **`tools.py`** — 22 tool definitions (get/find for 10 entities + `get_me`), error handling decorator, pagination metadata
  - Entities: companies, contacts, appointments, phone calls, orders, mail, activities, agreements, products, users
- **`serialize.py`** — `serialize()` converts Pydantic models to JSON via `model_dump()`, strips 50+ noise fields, supports sparse field selection and metadata
- **`filters.py`** — `transform_filters()` converts operator prefixes (`>=`, `>`, `<=`, `<`, `!=`, `*`) to Upsales API syntax, supports list values for range queries
- **`cache.py`** — Simple TTL cache (5 min) for user and product lookups that rarely change

Key patterns:
- **Error handling**: All tools wrapped with `@handle_errors` — SDK exceptions return `{"error": "...", "type": "..."}` instead of tracebacks
- **Pagination hints**: Find tools return `hasMore`, `nextOffset`, `remaining` in metadata when more results exist
- **Caching**: `get_user`, `find_users`, `get_product`, `find_products`, `get_me` are cached per API key for 5 minutes
- **Find tools** accept optional `filters`, `fields`, `sort`, `limit`, `offset` — filters is optional so they double as list tools

The `upsales` SDK dependency is pinned to a private GitHub repo (`AxelOhlander/upsales-python-sdk`). Docker builds require a `GITHUB_TOKEN` build arg to access it. For local development, switch `pyproject.toml` to `upsales = { path = "../upsales-python-sdk", editable = true }` for instant SDK changes without pushing.

## Known Workarounds

- **WEB-5366**: `f[]=value` on orders drops the field. Workaround: `_ORDER_FIELD_MAP` sends `f[]=orderValue` instead. Fix merged, expected live 2026-03-17.
- **WEB-5367**: Agreements endpoint crashes with any `f[]` param. Workaround: always include `metadata` in the fields list.

## Deployment

Deployed to Railway via Docker. Key env vars for hosted mode: `MCP_TRANSPORT=streamable-http`, `PORT` (Railway sets automatically), `AUTH_ISSUER_URL`, `AUTH_RESOURCE_URL`. For stdio mode: `UPSALES_API_KEY`, `UPSALES_USER_ID` (optional).

## Style

- Ruff for linting and formatting, line-length 100
- Hatch build system with `src/` layout
