"""Upsales CRM Chat Demo — login with Upsales, then chat via MCP."""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import anthropic
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

DEMO_DIR = Path(__file__).parent
PROJECT_DIR = DEMO_DIR.parent
UPSALES_API_BASE = "https://integration.upsales.com/api/v2"

# Single-user demo state
conversation: list[dict] = []
mcp_lock = asyncio.Lock()

SYSTEM_PROMPT = (
    "You are the Upsales CRM Assistant. You help sales teams find information in their CRM. "
    "You have access to Upsales CRM tools for reading companies, contacts, appointments, "
    "orders, and more. Be concise and helpful. Format data in readable tables when appropriate. "
    "When showing results, highlight the most important fields. "
    "If you use tools, briefly explain what you found — don't dump raw JSON."
)


def mcp_tools_to_anthropic(mcp_tools) -> list[dict]:
    """Convert MCP tool schemas to Anthropic API tool format."""
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema,
        }
        for tool in mcp_tools.tools
    ]


# ---------------------------------------------------------------------------
# MCP connection management — started lazily after login
# ---------------------------------------------------------------------------

# We need to keep the context managers alive, so we store the cleanup coroutine
_mcp_cleanup: asyncio.Task | None = None


async def _start_mcp(app: FastAPI, token: str, user_id: str = ""):
    """Start MCP server subprocess and connect the client."""
    await _stop_mcp(app)

    env = {**os.environ, "UPSALES_API_KEY": token}
    if user_id:
        env["UPSALES_USER_ID"] = user_id

    server_params = StdioServerParameters(
        command="uv",
        args=["--directory", str(PROJECT_DIR), "run", "upsales-mcp"],
        env=env,
    )

    # We need to keep the context managers open for the lifetime of the session.
    # Use an asyncio.Event to signal shutdown.
    shutdown_event = asyncio.Event()
    app.state.mcp_shutdown = shutdown_event
    ready_event = asyncio.Event()

    async def run_mcp():
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    app.state.mcp_session = session
                    app.state.anthropic_tools = mcp_tools_to_anthropic(tools_result)
                    print(f"MCP connected: {len(app.state.anthropic_tools)} tools available")
                    ready_event.set()
                    # Keep alive until shutdown
                    await shutdown_event.wait()
        except Exception as exc:
            print(f"MCP error: {exc}")
            ready_event.set()

    global _mcp_cleanup
    _mcp_cleanup = asyncio.create_task(run_mcp())
    # Wait for MCP to be ready (or fail)
    await asyncio.wait_for(ready_event.wait(), timeout=30)


async def _stop_mcp(app: FastAPI):
    """Stop the current MCP connection if running."""
    global _mcp_cleanup
    shutdown = getattr(app.state, "mcp_shutdown", None)
    if shutdown:
        shutdown.set()
    if _mcp_cleanup:
        try:
            await asyncio.wait_for(_mcp_cleanup, timeout=5)
        except (asyncio.TimeoutError, Exception):
            _mcp_cleanup.cancel()
        _mcp_cleanup = None
    app.state.mcp_session = None
    app.state.anthropic_tools = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan — MCP starts after login, not here."""
    app.state.mcp_session = None
    app.state.anthropic_tools = None
    app.state.user = None
    yield
    await _stop_mcp(app)


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(DEMO_DIR / "static")), name="static")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index():
    return (DEMO_DIR / "static" / "index.html").read_text()


@app.get("/api/status")
async def status(request: Request):
    """Check if user is logged in and MCP is connected."""
    user = request.app.state.user
    if user and request.app.state.mcp_session:
        return {"loggedIn": True, "user": user}
    return {"loggedIn": False}


@app.post("/api/login")
async def login(request: Request):
    """Login with Upsales email/password, start MCP with session token."""
    body = await request.json()
    email = body.get("email", "").strip()
    password = body.get("password", "")

    if not email or not password:
        return JSONResponse(status_code=400, content={"error": "Email and password required"})

    # Authenticate with Upsales
    async with httpx.AsyncClient() as http:
        try:
            resp = await http.post(
                f"{UPSALES_API_BASE}/session",
                json={"email": email, "password": password, "isMobile": True, "skipCookie": True},
                timeout=15,
            )
        except httpx.RequestError as exc:
            return JSONResponse(status_code=502, content={"error": f"Cannot reach Upsales: {exc}"})

    if resp.status_code != 200:
        # Parse error message from Upsales response
        try:
            err = resp.json()
            msg = err.get("error", {}).get("msg", "Login failed")
        except Exception:
            msg = f"Login failed (HTTP {resp.status_code})"
        return JSONResponse(status_code=401, content={"error": msg})

    data = resp.json().get("data", {})
    token = data.get("token")
    if not token:
        return JSONResponse(status_code=401, content={"error": "No token in response"})

    # Check for 2FA
    if data.get("isTwoFactorAuth"):
        return JSONResponse(
            status_code=401,
            content={"error": "Two-factor authentication is not supported in this demo"},
        )

    # Look up the user to get their ID and name
    user_info = {"email": email, "name": email, "id": None}
    async with httpx.AsyncClient() as http:
        try:
            users_resp = await http.get(
                f"{UPSALES_API_BASE}/users",
                params={"token": token, "email": email},
                timeout=10,
            )
            if users_resp.status_code == 200:
                users_data = users_resp.json().get("data", [])
                if users_data:
                    u = users_data[0]
                    user_info = {
                        "email": u.get("email", email),
                        "name": u.get("name", email),
                        "id": u.get("id"),
                    }
        except Exception:
            pass  # Non-critical, we can proceed without user details

    # Start MCP with the session token
    user_id = str(user_info["id"]) if user_info["id"] else ""
    try:
        await _start_mcp(request.app, token, user_id)
    except Exception as exc:
        return JSONResponse(
            status_code=500, content={"error": f"Failed to start CRM connection: {exc}"}
        )

    request.app.state.user = user_info
    conversation.clear()

    return {"ok": True, "user": user_info}


@app.post("/api/logout")
async def logout(request: Request):
    """Disconnect MCP and clear session."""
    await _stop_mcp(request.app)
    request.app.state.user = None
    conversation.clear()
    return {"ok": True}


@app.post("/api/chat")
async def chat(request: Request):
    if not request.app.state.mcp_session:
        return JSONResponse(status_code=401, content={"error": "Not logged in"})

    body = await request.json()
    user_message = body.get("message", "").strip()
    if not user_message:
        return {"error": "Empty message"}

    conversation.append({"role": "user", "content": user_message})

    async def stream():
        client = anthropic.AsyncAnthropic()
        session = request.app.state.mcp_session
        tools = request.app.state.anthropic_tools
        messages = list(conversation)

        while True:
            collected_text = ""
            tool_uses = []

            async with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            ) as stream_resp:
                async for event in stream_resp:
                    if event.type == "content_block_start":
                        if event.content_block.type == "tool_use":
                            tool_uses.append(
                                {
                                    "id": event.content_block.id,
                                    "name": event.content_block.name,
                                    "input": "",
                                }
                            )
                            yield f"event: tool_start\ndata: {json.dumps({'name': event.content_block.name})}\n\n"
                    elif event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            collected_text += event.delta.text
                            yield f"event: text\ndata: {json.dumps({'text': event.delta.text})}\n\n"
                        elif event.delta.type == "input_json_delta":
                            if tool_uses:
                                tool_uses[-1]["input"] += event.delta.partial_json

                final_message = await stream_resp.get_final_message()

            if final_message.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": final_message.content})

                tool_results = []
                for tu in tool_uses:
                    try:
                        args = json.loads(tu["input"]) if tu["input"] else {}
                    except json.JSONDecodeError:
                        args = {}

                    yield f"event: tool_call\ndata: {json.dumps({'name': tu['name'], 'args': args})}\n\n"

                    async with mcp_lock:
                        result = await session.call_tool(tu["name"], args)

                    result_text = ""
                    for content in result.content:
                        if hasattr(content, "text"):
                            result_text += content.text

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": result_text,
                        }
                    )

                    yield f"event: tool_result\ndata: {json.dumps({'name': tu['name']})}\n\n"

                messages.append({"role": "user", "content": tool_results})
                tool_uses = []
                continue

            if collected_text:
                conversation.append({"role": "assistant", "content": collected_text})
            yield f"event: done\ndata: {json.dumps({'done': True})}\n\n"
            break

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/reset")
async def reset():
    conversation.clear()
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=3000)
