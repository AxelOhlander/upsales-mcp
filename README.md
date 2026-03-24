# Upsales CRM MCP Server

MCP server that exposes Upsales CRM data as read-only tools. Supports 10 entity types with get/find operations, custom field resolution, and flexible filtering.

Supports two modes:
- **Local (stdio)**: API key from environment variable, for personal use
- **Hosted (Streamable HTTP)**: Each client sends their Upsales API key as a Bearer token, for multi-tenant deployment

## Setup

```bash
uv sync
```

## Local Usage (stdio)

### Claude Desktop / Claude Code

Add to your MCP config:

```json
{
  "mcpServers": {
    "upsales": {
      "command": "uv",
      "args": ["--directory", "/path/to/upsales-mcp", "run", "upsales-mcp"],
      "env": {
        "UPSALES_API_KEY": "your-api-key"
      }
    }
  }
}
```

### Standalone

```bash
UPSALES_API_KEY=your-key uv run upsales-mcp
```

## Hosted Deployment (Railway)

Each user authenticates with their own Upsales API key via `Authorization: Bearer <upsales-api-key>`.

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MCP_TRANSPORT` | Yes | `stdio` | Set to `streamable-http` for hosted mode |
| `PORT` | No | `8000` | HTTP port (Railway sets this automatically) |
| `UPSALES_USER_ID` | No | — | Current user's Upsales ID (enables "my meetings" queries) |

### Deploy to Railway

1. Push this repo to GitHub
2. Create a new Railway project from the repo
3. Set `MCP_TRANSPORT=streamable-http` in environment variables
4. Set `AUTH_ISSUER_URL` and `AUTH_RESOURCE_URL` to your Railway deployment URL
5. Deploy

### Client Configuration (Remote)

```json
{
  "mcpServers": {
    "upsales": {
      "type": "streamable-http",
      "url": "https://your-app.up.railway.app/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_UPSALES_API_KEY"
      }
    }
  }
}
```

## Available Tools

Each entity has a `get_*` tool (by ID) and a `find_*` tool (search/list with filters, pagination, field selection).

| Entity | Get | Find | Custom Fields |
|--------|-----|------|---------------|
| Companies | `get_company` | `find_companies` | Yes |
| Contacts | `get_contact` | `find_contacts` | Yes |
| Appointments | `get_appointment` | `find_appointments` | Yes |
| Phone Calls | `get_phone_call` | `find_phone_calls` | — |
| Orders | `get_order` | `find_orders` | Yes |
| Mail | `get_mail` | `find_mail` | — |
| Activities | `get_activity` | `find_activities` | Yes |
| Agreements | `get_agreement` | `find_agreements` | Yes |
| Products | `get_product` | `find_products` | Yes |
| Users | `get_user` | `find_users` | — |

Plus: `get_me` (current user profile) and `find_custom_fields` (discover custom field definitions for any entity).

### Custom Fields

Entities with custom fields show resolved values inline:

```json
{
  "id": 123,
  "name": "Acme Corp",
  "customFields": {
    "Industry": {"value": "SaaS", "fieldId": 11, "type": "Select"},
    "Delivery Date": {"value": "2026-03-14", "fieldId": 42, "type": "Date"}
  }
}
```

Use `find_custom_fields("company")` to discover available fields, then filter with `custom.FIELD_ID` syntax:

```json
{"custom.42": ">=2026-04-14"}
```

### Field Selection

Use the `fields` parameter to reduce response size. Supports dot-notation for nested data:

```json
fields: ["id", "description", "value", "orderRow.product.name", "orderRow.price"]
```

## Filter Operators

All find tools accept a `filters` dict with these operators:

| Syntax | Meaning |
|--------|---------|
| `{"field": value}` | Equals |
| `{"field": ">=value"}` | Greater than or equals |
| `{"field": ">value"}` | Greater than |
| `{"field": "<=value"}` | Less than or equals |
| `{"field": "<value"}` | Less than |
| `{"field": "!=value"}` | Not equals |
| `{"field": "*value"}` | Contains (substring) |

For range queries on the same field, use a list:

```json
{"date": [">=2026-03-01", "<=2026-03-31"]}
```

### Examples

```json
// Active companies containing "Acme"
{"name": "*Acme", "active": 1}

// Contacts at a specific company
{"client.id": 123}

// Orders since 2024 with >50% probability
{"date": ">=2024-01-01", "probability": ">=50"}

// Planned meetings for a user
{"outcome": "planned", "user.id": 5}

// Orders with custom field 42 on or after a date
{"custom.42": ">=2026-04-14"}
```
