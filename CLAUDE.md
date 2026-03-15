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

- **FastMCP instance** (`mcp`) registered with 15 tools: get/list/search for each of 5 entities (companies, contacts, appointments, phone calls, orders)
- **Auth**: In hosted mode, `BearerAuthMiddleware` extracts the Upsales API key from the Authorization header and stores it in a `contextvars.ContextVar`. In stdio mode, reads `UPSALES_API_KEY` from env.
- **`_get_client()`** creates a new `Upsales` SDK client per request using the resolved API key
- **`_serialize()`** converts Pydantic models to JSON via `model_dump()`, excluding `custom_fields`
- **Search tools** accept a `filters` dict with operator prefixes (`>=`, `>`, `<=`, `<`, `!=`, `*` for contains)
- **All list/search tools** accept a `fields` parameter for sparse field selection

The `upsales` SDK dependency is pinned to a private GitHub repo (`AxelOhlander/upsales-python-sdk`). Docker builds require a `GITHUB_TOKEN` build arg to access it.

## Deployment

Deployed to Railway via Docker. Key env vars for hosted mode: `MCP_TRANSPORT=streamable-http`, `PORT` (Railway sets automatically), `AUTH_ISSUER_URL`, `AUTH_RESOURCE_URL`.

## Style

- Ruff for linting and formatting, line-length 100
- Hatch build system with `src/` layout
