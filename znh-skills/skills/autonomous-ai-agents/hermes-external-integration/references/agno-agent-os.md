# Agno AgentOS Integration Reference

Condensed reference for integrating Hermes with Agno AgentOS. Derived from docs, source inspection, and the `ClaudeAgent` adapter implementation.

## What AgentOS Is

AgentOS is a FastAPI runtime + web control plane for multi-agent systems.
- **Runtime**: FastAPI app with 50+ endpoints, SSE streaming, JWT RBAC.
- **Control Plane**: Browser UI for chat, traces (tree + waterfall views), sessions, approvals, knowledge, memories, schedules.
- **Data Ownership**: All sessions, memory, knowledge, traces stored in *your* database (SQLite or Postgres). Agno stores no data except your runtime endpoint.
- **Private by Design**: Control plane connects directly from browser to your runtime. No proxies, no data relays.

## External Agent Protocol

AgentOS supports adapters for non-Agno agents via `BaseExternalAgent` (in `libs/agno/agno/agents/base.py`).

### Required Hooks (subclass must implement)

```python
async def _arun_adapter(self, input, *, history=None, **kwargs) -> Any:
    """Non-streaming. Return response content.
    kwargs includes 'session' (AgentSession or None).
    Mutate session.session_data in place for persistence.
    """


async def _arun_adapter_stream(
    self, input, *, history=None, **kwargs
) -> AsyncIterator[RunOutputEvent]:
    """Streaming. Yield RunContentEvent, ToolCallStartedEvent, etc.
    Do NOT yield RunStartedEvent or RunCompletedEvent — base class handles those.
    """
```

### Base Class Handles
- `RunStartedEvent` / `RunCompletedEvent` / `RunErrorEvent` emission
- Session persistence (`read_or_create_session`, `upsert_session`)
- Tool call event wrapping (`ToolCallStartedEvent`, `ToolCallCompletedEvent`)
- Sync/async execution wrappers (`run` / `arun`)
- Terminal output formatting (`print_response`, `aprint_response`)

### Key Attributes
- `name` — display name
- `id` — auto-generated from name if omitted
- `framework` — string identifier (e.g., `"hermes"`)
- `db` — `BaseDb` or `AsyncBaseDb` for session persistence
- `markdown` — whether to render as Markdown in terminal

## Persistent Worker Pattern (Performance)

Hermes is a Python CLI — each invocation pays a ~1–2 s interpreter cold-start cost. When the adapter fires a subprocess per message, this overhead is paid every single time.

**Solution**: A persistent worker process that stays alive across requests.

### How it works
1. The adapter starts a long-lived `hermes_worker.py` process per session.
2. Requests are sent to the worker via `stdin` as JSON lines.
3. The worker runs `hermes chat` and streams stdout chunks back as JSON lines.
4. The adapter reads chunks in real-time and yields `RunContentEvent` to the UI.

### Why it helps
- Python interpreter stays warm (no import cost on subsequent requests).
- The OS has already cached the `hermes` binary in memory.
- Each message still spawns `hermes chat` (Hermes is one-shot), but the ~1–2 s interpreter startup is eliminated.
- Streaming is supported because the worker reads stdout line-by-line as Hermes produces it.

### Implementation
See `templates/external-agent-adapter.py` for the full adapter and `templates/hermes_worker.py` for the worker. The adapter:
- Starts a worker on first use via `asyncio.create_subprocess_exec`.
- Sends requests as JSON lines on the worker's stdin.
- Reads responses as JSON lines from the worker's stdout.
- Yields `RunContentEvent` per chunk so the UI shows a typing effect.
- Handles worker restarts if the process dies.

## Real-Time Streaming Implementation

Agno's UI expects SSE events. The adapter must yield `RunContentEvent` chunks as they arrive, not buffer the entire response.

### Key pattern
```python
async for event in self._arun_adapter_stream(input, **kwargs):
    if isinstance(event, RunContentEvent):
        yield event  # UI receives this immediately via SSE
```

### Gotcha: Hermes quiet mode
`hermes chat -Q` buffers ALL output internally and only dumps it when the process exits. So even though the adapter reads stdout in real-time, Hermes itself may deliver the response as a single block.

**Workaround**: The persistent worker reads stdout line-by-line. If Hermes emits lines incrementally, those are forwarded immediately. If it dumps everything at once, the worker forwards it in one chunk. Either way, the UI receives something rather than waiting 40s in silence.

### Speed comparison
| Approach | Time per message | Notes |
|---|---|---|
| `subprocess.run()` per message | ~40-45s | Interpreter cold-start + full buffer |
| Persistent worker | ~35s | Warm interpreter, streaming ready |
| With `max_turns=3` | ~35s | Down from 10, fewer tool calls |

Further improvements require Hermes itself to support token streaming (not available as of this writing).

## ClaudeAgent as Reference Implementation

`ClaudeAgent` (`libs/agno/agno/agents/claude/agent.py`) wraps the Claude Agent SDK subprocess.

### Session ID Mapping
```python
_sdk_session_ids: Dict[str, str]  # Agno session_id -> SDK session_id
```
This prevents cross-session bleed and enables resume across restarts.

### Non-Streaming Flow
1. Build `ClaudeAgentOptions` from agent fields.
2. Call `sdk.query(prompt=str(input), options=options)`.
3. On `SystemMessage(subtype="init")`, extract `session_id` and store in `_sdk_session_ids`.
4. Accumulate `TextBlock.text` from `AssistantMessage`s.
5. Return `ResultMessage.result` if present, else accumulated text.

### Streaming Flow
1. Set `include_partial_messages=True` in options.
2. Iterate SDK messages:
   - `StreamEvent(type="content_block_delta", delta_type="text_delta")` → `RunContentEvent`
   - `AssistantMessage` with `ToolUseBlock` → `ToolCallStartedEvent`
   - `UserMessage` with `ToolResultBlock` → `ToolCallCompletedEvent`
   - `ResultMessage` → validate and capture `session_id`
3. Text blocks from `AssistantMessage` are only emitted if no `StreamEvent`s were received (prevents duplication).

## Multi-Framework Capability Matrix

| Capability | External Adapter | Notes |
|---|---|---|
| AgentOS registration | ✅ | Adapters satisfy `AgentProtocol` |
| `/agents/{id}/runs` endpoints | ✅ | Same routes as native |
| SSE streaming | ✅ | If adapter yields events |
| Session persistence | ✅ | When `db` is set on AgentOS |
| Tool call visibility in UI | ✅ | Must wrap as Agno tool events |
| Use as `Team` member | ❌ | Teams only support native `Agent` |
| Memory, knowledge, guardrails | ❌ | Native-only features |
| Structured I/O | ❌ | Use framework's own typing |
| Skills, reasoning, learning | ❌ | Native `Agent` only |

## Database Expectations

AgentOS uses Agno's DB layer (`BaseDb` / `AsyncBaseDb`). Implementations:
- `SqliteDb(db_file="...")`
- `PostgresDb(...)`

The DB stores:
- `AgentSession` — session metadata, `session_data` JSON blob (adapter-specific state goes here)
- `Run` / trace tables — event-level traces for the control plane tree/waterfall views
- Knowledge, memory, schedules (native-only; external adapters don't populate these)

### Critical: AgentOS requires a DB
If you instantiate `AgentOS(agents=[...])` without passing `db=...`, the OS will raise `StopIteration` when any endpoint tries to look up the default database (e.g., `POST /sessions`, `GET /sessions`).

```python
from agno.db.sqlite.sqlite import SqliteDb

agent_os = AgentOS(
    agents=[agent],
    db=SqliteDb(db_file="/tmp/agno_os.db"),  # Required!
)
```

When writing a trace bridge (Pattern 2), you write to the same tables AgentOS reads from.

## Key Endpoints (Runtime)

| Endpoint | Purpose |
|---|---|
| `GET /` | Control plane connection |
| `GET /docs` | OpenAPI docs |
| `POST /agents/{agent_id}/runs` | Run an agent |
| `POST /teams/{team_id}/runs` | Run a team |
| `POST /workflows/{workflow_id}/runs` | Run a workflow |

All routes require `Authorization: Bearer <token>` when a Security Key is configured.

## Self-Hosted UI with Path Prefix (Reverse Proxy)

When the AgentOS runtime is behind a reverse proxy with a path prefix (e.g., Tailscale `serve /agno`), the UI must be built with the matching `basePath` or all asset URLs will 404.

### Build with basePath
```typescript
// next.config.ts
const nextConfig = {
  output: 'export',
  basePath: '/agno',  // Must match reverse proxy path
}
```
This rewrites all `_next` asset references from `/_next/...` to `/agno/_next/...`.

### FastAPI Serving Pattern (API + UI coexistence)
The runtime's root `/` returns API JSON. Browsers need HTML. Use content negotiation:

```python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

static_dir = "/path/to/agent-ui/dist"

# 1. Mount static assets at ROOT (not under /ui)
#    The basePath makes URLs /agno/_next/..., so the backend
#    must serve _next at /_next, not /agno/_next
app.mount(
    "/_next", StaticFiles(directory=os.path.join(static_dir, "_next")), name="assets"
)


# 2. Serve favicon
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(os.path.join(static_dir, "favicon.ico"))


# 3. Middleware: serve HTML for browser requests, preserve API for others
class BrowserUIMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/" and "text/html" in request.headers.get("accept", ""):
            return FileResponse(os.path.join(static_dir, "index.html"))
        return await call_next(request)


app.add_middleware(BrowserUIMiddleware)


# 4. SPA catchall for client-side routing (after all API routes)
@app.get("/{path:path}", include_in_schema=False)
async def spa_catchall(path: str):
    return FileResponse(os.path.join(static_dir, "index.html"))
```

### Why this works
- API clients (curl, SDKs) hit `/` without `Accept: text/html` → get JSON API metadata
- Browsers hit `/` with `Accept: text/html` → get the AgentUI HTML
- The UI loads assets from `/_next/...` which the mount handles
- Client-side routing (React Router) hits `/{path:path}` and gets `index.html`

### Auto-Connect UI to Runtime
The self-hosted UI starts with an empty endpoint. Inject an auto-detect script into the built `index.html`:

```html
<script>
if (!localStorage.getItem("os-endpoint")) {
    localStorage.setItem("os-endpoint", window.location.origin);
}
</script>
```

Place this immediately after `<head>` so it runs before the React app initializes. This sets the endpoint to whatever URL the user visited — Tailscale domain, localhost, or any reverse-proxied origin.

### Pitfalls
1. **StaticFiles + catchall conflict**: Do NOT mount `StaticFiles` at `/ui` AND register `@app.get("/ui/{path:path}")`. FastAPI prioritizes exact routes over mounts, causing infinite 307 redirects.
2. **Missing basePath**: Without `basePath`, the UI requests `/_next/...` but the proxy only forwards `/agno/_next/...` — all assets 404.
3. **Wrong PROJECT_ROOT**: When the server script lives in `agent_context/scripts/`, resolving the static dir requires 3× `dirname` (script → agent_context → project_root), not 2×.
4. **Caching**: If the user loaded the UI before the auto-connect script was injected, the empty `os-endpoint` is cached in localStorage. They must hard-refresh (Ctrl+F5) or delete the localStorage key.
5. **Tailscale path stripping**: Tailscale `serve /agno` strips `/agno` before forwarding. The backend sees `/`, not `/agno/`. The `basePath` handles this because the browser constructs URLs relative to the origin, and the proxy re-attaches `/agno` to outgoing requests.

### Verification Checklist
After deployment, verify all three independently:
```bash
# 1. UI HTML loads
curl -H "Accept: text/html" https://domain.com/agno

# 2. API still works
curl https://domain.com/agno/agents

# 3. Static assets load
curl -I https://domain.com/agno/_next/static/css/...
```

## Connecting os.agno.com to a Local AgentOS Instance

**Free-tier constraint:** The hosted Agno Control Plane at `https://os.agno.com` connects to your local AgentOS. The **free tier only allows `localhost` endpoints** — custom domains/Tailscale URLs require a paid Pro plan ($150/mo + $95/mo per external connection). If the user says they want the free tier, `localhost:9120` is the only viable endpoint. Do not suggest Tailscale URLs or custom domains as alternatives for free-tier users.

The Agno Control Plane at `https://os.agno.com` is a hosted web app that connects directly to your local AgentOS runtime. Because `os.agno.com` is served over HTTPS, browsers enforce **mixed-content policy** — an HTTPS page cannot call an HTTP API (`http://localhost:9120`). AgentOS must therefore serve HTTPS locally.

### Step 1: Enable HTTPS on AgentOS

Generate a certificate and patch `serve_agno.py` to use it. See `pantheon-exposure` skill → `references/cors-ssl-patch.md` for the exact CORS + SSL code patches.

### Step 2: The Self-Signed Cert Trap

Using `openssl req -x509 ...` creates a self-signed certificate that:
- ✅ Works when you visit `https://localhost:9120` directly in a browser tab (you can click "Advanced → Proceed")
- ❌ **Fails** when `os.agno.com` tries to `fetch()` that URL from JavaScript

The browser's manual trust only applies to the current tab's navigation. Cross-origin `fetch()` / `XMLHttpRequest` still sees the cert as untrusted and throws `NET::ERR_CERT_AUTHORITY_INVALID`.

**Symptom:** You can open `https://localhost:9120` in a tab and see JSON, but `os.agno.com` shows a loading spinner or connection error.

### Solutions

| Approach | Effort | Works for os.agno.com? | Free tier? |
|---|---|---|---|
| `mkcert` | Low (install once) | ✅ Yes | ✅ Yes |
| Chrome `--allow-insecure-localhost` | None | ✅ Yes — for that session only | ✅ Yes |
| Tailscale URL (`https://<host>.ts.net/agno`) | None | ✅ Yes — but **requires Pro plan** | ❌ No |
| `openssl` self-signed | Low | ❌ No — only works for direct navigation | ✅ Yes |

#### Option A: mkcert (Recommended, Free Tier)

`mkcert` creates a local CA. On Linux/WSL, the CA is installed under `~/.local/share/mkcert/`. The browser on the Windows side must trust this CA for cross-origin `fetch()` to work.

**Step 1: Install mkcert (no sudo needed)**

```bash
mkdir -p ~/.local/bin
curl -sL "https://dl.filippo.io/mkcert/latest?for=linux/amd64" -o ~/.local/bin/mkcert
chmod +x ~/.local/bin/mkcert
export PATH="$HOME/.local/bin:$PATH"
```

**Step 2: Generate a cert for localhost**

```bash
mkdir -p /mnt/z/pantheon/.agno-certs
cd /mnt/z/pantheon/.agno-certs
mkcert localhost 127.0.0.1 ::1
# Creates: localhost+2.pem  localhost+2-key.pem
```

**Step 3: Trust the CA on Windows (critical for os.agno.com)**

On WSL, `mkcert -install` fails without sudo, so trust the CA manually:

```bash
# Copy the root CA to the Windows Desktop
cp ~/.local/share/mkcert/rootCA.pem "/mnt/c/Users/<username>/Desktop/agno-local-ca.pem"
```

On Windows:
1. Double-click `agno-local-ca.pem` on the Desktop
2. Click **Install Certificate** → **Local Machine**
3. **Place all certificates in the following store** → Browse → select **Trusted Root Certification Authorities**
4. Click through the security warning and finish
5. **Restart your browser**

**Step 4: Start AgentOS with the mkcert files**

```bash
export AGNO_SSL_KEYFILE=/mnt/z/pantheon/.agno-certs/localhost+2-key.pem
export AGNO_SSL_CERTFILE=/mnt/z/pantheon/.agno-certs/localhost+2.pem
cd /mnt/z/pantheon/projects/purple-phoenix/main/agent_context/scripts
uv run --active python serve_agno.py
```

#### Option B: Chrome Flag (Quick)

Close all Chrome windows, then from PowerShell:
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --allow-insecure-localhost
```

#### Option C: Tailscale URL (Simplest, but requires Pro plan)

Skip local certs entirely. Point `os.agno.com` to `https://<host>.<tailnet>.ts.net/agno`. Tailscale's HTTPS is already valid.

**Only works on Agno Pro plan** — the free tier restricts connections to `localhost`. Do not suggest this to users who want the free tier.

### WSL localhost forwarding

WSL2 automatically forwards `localhost:9120` from Windows to WSL's `127.0.0.1:9120`. Entering `https://localhost:9120` on your Windows browser correctly hits the WSL service.

### Verification

```bash
# 1. HTTPS is responding
curl -sk https://127.0.0.1:9120 | python3 -m json.tool

# 2. CORS headers are present
curl -sk -D - -o /dev/null -H "Origin: https://os.agno.com" https://127.0.0.1:9120/ | grep -i access-control

# 3. Browser console shows no cert errors when os.agno.com connects
```

## Performance Tuning

### Reduce max_turns
`--max-turns` controls how many agentic thinking loops Hermes performs. The default of 10 means a simple question may trigger 10 tool calls. Lower this to 2-3 for conversational agents where tool depth is not needed.

```python
agent = HermesAgent(name="Hermes Coder", max_turns=3)
```

Trade-off: fewer turns means faster responses but less deep reasoning. Profile with your workload and adjust.

### Profile your stack
- Is the delay in Python startup? → Use persistent worker.
- Is the delay in model inference? → Switch to a faster model.
- Is the delay in tool calls? → Reduce `max_turns` or cache tool results.

## Install & Quick Start

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -U 'agno[os]' anthropic   # or your model provider

export ANTHROPIC_API_KEY=sk-***
python your_agent_os.py
# Serves on http://localhost:8000
```

Minimal AgentOS:
```python
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.anthropic import Claude
from agno.os import AgentOS

agent = Agent(
    name="Agno Assist",
    model=Claude(id="claude-sonnet-4-5"),
    db=SqliteDb(db_file="agno.db"),
)
agent_os = AgentOS(agents=[agent])
app = agent_os.get_app()
```

## Useful Links

- Docs: https://docs.agno.com/agent-os/introduction
- Multi-Framework: https://docs.agno.com/agent-os/multi-framework/overview
- Control Plane: https://docs.agno.com/agent-os/control-plane
- GitHub: https://github.com/agno-agi/agno
- Cookbook (framework integrations): https://github.com/agno-agi/agno/tree/main/cookbook/frameworks
