# Upsales CRM MCP Server

MCP server that exposes Upsales CRM data (companies, contacts, appointments, phone calls, orders) as read-only tools.

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
| `AUTH_ISSUER_URL` | No | `https://upsales-mcp.up.railway.app` | OAuth issuer URL for metadata |
| `AUTH_RESOURCE_URL` | No | `https://upsales-mcp.up.railway.app` | OAuth resource server URL |

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

| Tool | Description |
|------|-------------|
| `get_company` | Get a company by ID |
| `list_companies` | List companies with pagination |
| `search_companies` | Search companies with filters |
| `get_contact` | Get a contact by ID |
| `list_contacts` | List contacts with pagination |
| `search_contacts` | Search contacts with filters |
| `get_appointment` | Get an appointment/meeting by ID |
| `list_appointments` | List appointments with pagination |
| `search_appointments` | Search appointments with filters |
| `get_phone_call` | Get a phone call by ID |
| `list_phone_calls` | List phone calls with pagination |
| `search_phone_calls` | Search phone calls with filters |
| `get_order` | Get an order by ID |
| `list_orders` | List orders with pagination |
| `search_orders` | Search orders with filters |

## Search Filter Operators

All search tools accept a `filters` dict with these operators:

| Syntax | Meaning |
|--------|---------|
| `{"field": value}` | Equals |
| `{"field": ">=value"}` | Greater than or equals |
| `{"field": ">value"}` | Greater than |
| `{"field": "<=value"}` | Less than or equals |
| `{"field": "<value"}` | Less than |
| `{"field": "!=value"}` | Not equals |
| `{"field": "*value"}` | Contains (substring) |

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
```
