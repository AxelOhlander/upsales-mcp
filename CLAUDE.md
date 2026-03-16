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

No test suite exists yet.

## Architecture

Single-file server at `src/upsales_mcp/server.py`. All logic lives here:

- **FastMCP instance** (`mcp`) registered with 21 tools: get/find for each of 10 entities + `get_me`
  - Entities: companies, contacts, appointments, phone calls, orders, mail, activities, agreements, products, users
- **Auth**: In hosted mode, `BearerAuthMiddleware` extracts the Upsales API key from the Authorization header and stores it in a `contextvars.ContextVar`. In stdio mode, reads `UPSALES_API_KEY` from env.
- **User identity**: `UPSALES_USER_ID` env var injects user context into MCP instructions so "my meetings" queries work. `get_me` tool returns the current user's profile.
- **`_get_client()`** creates a new `Upsales` SDK client per request using the resolved API key
- **`_serialize()`** converts Pydantic models to JSON via `model_dump()`, strips 50+ noise fields, supports sparse field selection and metadata (`{"metadata": {"total": N, "count": N}, "data": [...]}`)
- **`_transform_filters()`** converts operator prefixes (`>=`, `>`, `<=`, `<`, `!=`, `*`) to Upsales API syntax, supports list values for range queries on the same field (e.g. `{"date": [">=2025-01-01", "<=2025-01-31"]}`)
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
