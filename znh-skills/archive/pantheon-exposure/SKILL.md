---
name: pantheon-exposure
description: Start, stop, and verify the Pantheon unified dashboard stack — Hermes dashboard + Agno AgentOS + Tailscale paths. Use when the user asks "is agno running", "start the dashboard", "pantheon expose", or any question about the unified dashboard/exposure stack.
version: 1.0.0
author: Hermes Agent
tags: [pantheon, hermes, agno, tailscale, dashboard, exposure, serve]
related_skills: [tailscale-serve-localhost, hermes-external-integration, hermes-agent]
---

# Pantheon Unified Dashboard / Exposure Stack

Manages the four-layer local serving stack that makes Hermes, Phoenix, and Agno reachable from the Tailscale tailnet:

1. **Hermes dashboard** — port 9119 (path `/hermes`)
2. **Phoenix observability** — port 6006 (path `/phoenix`)
3. **Agno AgentOS** — port 9120 (path `/agno`)
4. **Tailscale serve** — proxies all three ports to `https://<host>.<tailnet>.ts.net/...`

## Trigger Conditions

- User asks "is agno running" or "is the dashboard running" or "is phoenix running"
- User says "start pantheon expose" or "pantheon expose start"
- User wants to verify or restart the unified dashboard stack
- Any question about Tailscale `/hermes`, `/phoenix`, or `/agno` URLs

## Quick Reference

```bash
# Check current status
pantheon expose status

# Start everything (preferred — if it works)
pantheon expose start

# Check ports directly
ss -tlnp | grep -E '9119|6006|9120'
curl -s http://127.0.0.1:9119/hermes | head -1
curl -s http://127.0.0.1:6006 | head -1
curl -s http://127.0.0.1:9120 | python3 -m json.tool
```

## Status Check (always run first)

```bash
pantheon expose status
```

Typical output:
```
Hermes dashboard  : stopped (port 9119)
Phoenix           : stopped (port 6006)
Agno AgentOS      : stopped (port 9120)
Tailscale /hermes : registered
Tailscale /phoenix: registered
Tailscale /agno   : registered
```

If all three services show "running", the stack is up. If any is stopped, proceed to startup.

## Startup — Layer by Layer

### Layer 1: Hermes Dashboard (port 9119)

**Pitfall:** `hermes dashboard` has NO `run` subcommand. The CLI is:
```bash
# WRONG ❌
hermes dashboard run --no-open ...

# CORRECT ✅
hermes dashboard --no-open --skip-build --insecure --host 0.0.0.0 --port 9119
```

**Environment variable:** `HERMES_DASHBOARD_PREFIX=/hermes` tells the dashboard it's behind a path prefix. Without this, asset URLs will break when served through Tailscale `/hermes`.

**Background start:**
```bash
HERMES_DASHBOARD_PREFIX=/hermes hermes dashboard --no-open --skip-build --insecure --host 0.0.0.0 --port 9119
```

Wait ~5 seconds, then verify:
```bash
curl -s http://127.0.0.1:9119/hermes | head -3
# Should return HTML (<!doctype html>...)
```

### Layer 2: Phoenix Observability (port 6006)

**Pantheon main branch already includes Phoenix** in `pantheon expose`. It starts via `uvx --from arize-phoenix phoenix serve` on port 6006 and sets `PHOENIX_HOST_ROOT_PATH=/phoenix` so the UI is served under the `/phoenix` path prefix.

**Verify:**
```bash
curl -s http://127.0.0.1:6006 | head -1
# Should return HTML (<!doctype html>...)
```

**Tailscale path:** `https://<host>.<tailnet>.ts.net/phoenix`

**Note:** When Phoenix is already running independently (e.g. started manually from the Hermes venv), `pantheon expose` detects the open port and skips starting a second instance.

### Layer 3: Agno AgentOS (port 9120)

**Path:** `projects/purple-phoenix/main/agent_context/scripts/serve_agno.py`

**Pitfall:** The script is NOT at the project root. The canonical path is:
```
/mnt/z/pantheon/projects/purple-phoenix/main/agent_context/scripts/serve_agno.py
```

**Dependency:** `agno[os]` must be installed in the project's venv. If missing, the script exits with:
```
AgentOS not available. Install the web stack:
  pip install 'agno[os]'
```

Install with uv:
```bash
cd /mnt/z/pantheon/projects/purple-phoenix/main
uv pip install 'agno[os]'
```

**Pitfall:** When running `serve_agno.py` from outside the project root, uv may complain:
```
warning: `VIRTUAL_ENV=...` does not match the project environment path...
```

Use `--active` to force the project's venv:
```bash
cd /mnt/z/pantheon/projects/purple-phoenix/main/agent_context/scripts
uv run --active python serve_agno.py
```

**Pitfall (WSL2):** The server must bind to `0.0.0.0`, not `127.0.0.1`. When started via `pantheon expose start`, `_start_agno()` hardcodes `AGNO_HOST=127.0.0.1` which breaks WSL2 `networkingMode=Mirrored`. Patch `pantheon_init.py` or set the env explicitly:
```bash
export AGNO_HOST=0.0.0.0
```

Wait ~5 seconds, then verify:
```bash
curl -s http://127.0.0.1:9120 | python3 -m json.tool
# Should return {"name":"AgentOS API", ...}
```

### Layer 4: Tailscale Paths

The paths `/hermes`, `/phoenix`, and `/agno` are typically registered once and persist across restarts. Verify:

```bash
tailscale serve status
```

If missing, re-register:
```bash
tailscale serve --bg http://127.0.0.1:9119 /hermes
tailscale serve --bg http://127.0.0.1:6006 /phoenix
tailscale serve --bg http://127.0.0.1:9120 /agno
```

## Troubleshooting Guide

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `pantheon expose start` times out | Unknown — command not yet fully reliable | Use manual layer-by-layer startup |
| `hermes dashboard: error: invalid choice: 'run'` | Used `run` subcommand that doesn't exist | Drop `run` — `hermes dashboard --no-open ...` |
| `No such file or directory` for serve_agno.py | Wrong path assumption | Use full path under `projects/purple-phoenix/main/agent_context/scripts/` |
| `AgentOS not available` | `agno[os]` not installed | `uv pip install 'agno[os]'` in project root |
| `VIRTUAL_ENV does not match` | Running from wrong cwd without `--active` | Use `uv run --active python serve_agno.py` |
| Tailscale 502 on `/hermes`, `/phoenix`, or `/agno` | Local server not actually listening | Check `ss -tlnp` and `curl localhost:PORT` |
| Dashboard white screen (HTML loads, JS/CSS 404) | Tailscale strips `/hermes` prefix but does NOT inject `X-Forwarded-Prefix` header; dashboard serves absolute `/assets/...` URLs | Set `HERMES_DASHBOARD_PREFIX=/hermes` AND patch `web_server.py` to read env var (see "Dashboard Path Prefix" below) |
| Dashboard assets 404 | Missing `HERMES_DASHBOARD_PREFIX=/hermes` | Restart dashboard with env var set |
| Tailscale 502 on `/agno` | Agno serves HTTPS but Tailscale proxy is `http://` (protocol mismatch) | Change Tailscale to `https+insecure://127.0.0.1:9120` (see "Agno HTTPS + Tailscale" below) |
| Agno unreachable from Windows but `ss` shows port open | `_start_agno()` hardcodes `AGNO_HOST=127.0.0.1` which WSL2 mirrored networking cannot forward | Patch to `AGNO_HOST=0.0.0.0` (see "WSL2 binding" in PNA section below) |
| `os.agno.com` can't connect to `localhost:9120` | **PNA block** — Chrome blocks public origins from accessing loopback | See "PNA for os.agno.com Free Tier" below |
| Tailscale 502 on `/agno` | Agno serves HTTPS but Tailscale proxy is `http://` (protocol mismatch) | Change Tailscale to `https+insecure://127.0.0.1:9120` (see "Agno HTTPS + Tailscale" below) |
| Phoenix fails to start (no port 6006 binding, silent exit) | `anthropic` package version conflict in Hermes venv. Phoenix's `pydantic-ai-slim` requires a newer `anthropic` than what's installed | Upgrade `anthropic` in the Hermes venv: `uv pip install --python venv/bin/python 'anthropic>=0.40.0'`. Check logs for `AsyncAnthropicBedrockMantle` import errors |
| Phoenix starts but curl times out | Phoenix loading dependencies on first startup (takes 30–60s) | Wait longer; if still failing, check `~/.local/share/pantheon-stack/phoenix.log` |
| Phoenix UI shows `--` in input/output columns | Spans missing `input.value` and `output.value` attributes | Update the Phoenix plugin's `on_pre_api_request` / `on_post_api_request` / `on_pre_tool_call` / `on_post_tool_call` hooks to set `input.value`, `output.value`, and their `mime_type` counterparts. See `references/phoenix-observability.md` |
| systemd service stuck in "activating" or exits too early | `Type=simple` with no startup timeout; Phoenix needs 60–90s to bind on WSL drvfs | Change to `Type=oneshot` with `TimeoutStartSec=180` and add `_wait_for_port()` polling inside the start script. See `references/systemd-auto-start.md` |

## PNA (Private Network Access) for os.agno.com Free Tier

**Pitfall:** `os.agno.com` free tier requires `localhost:9120`. Tailscale URLs or custom domains are Pro-only. This means:
- You CANNOT use HTTPS/Tailscale to bypass the issue
- You MUST serve HTTP on `localhost:9120`
- Chrome's **Private Network Access (PNA)** policy blocks `https://os.agno.com` from fetching `http://localhost:9120`

**The error in browser console:**
```
Access to fetch at 'http://localhost:9120/health' from origin 'https://os.agno.com'
has been blocked by CORS policy: Permission was denied for this request to access
the `loopback` address space.
```

**The fix** — Pass `cors_allowed_origins` to `AgentOS(...)` instead of manually adding `CORSMiddleware`. Duplicate CORS middlewares produce conflicting `Access-Control-Allow-Origin` headers that Chrome rejects. Then add a thin pure-ASGI PNA middleware — **not `BaseHTTPMiddleware`** — because `BaseHTTPMiddleware` buffers response bodies, which breaks SSE streaming from AgentOS.

**Fetch spec compliance:** When `allow_credentials=True`, wildcard `Access-Control-Allow-Headers: *` and `Access-Control-Allow-Methods: *` violate the Fetch spec §3.2.3. The PNA preflight MUST echo back the actual requested method and headers. The server must also validate the Origin against an explicit allowlist; unknown origins get 403.

The current `serve_agno.py` implementation (commit `6e0240a` and later) uses:
- `AgentOS(cors_allowed_origins=["https://os.agno.com"])` for standard CORS
- Pure ASGI `PrivateNetworkAccessMiddleware` for PNA preflights
- Origin validation against `_PNA_ALLOWED_ORIGINS = frozenset({"https://os.agno.com"})`
- `BrowserUIMiddleware` also as pure ASGI (same non-buffering reason)

See `references/pna-serve-agno.md` for the complete current code.

**WSL2 binding:** The server must also bind to `0.0.0.0` (not `127.0.0.1`) so Windows can reach WSL localhost. See `wsl-localhost` skill.

**Pitfall in `pantheon_init.py`:** `_start_agno()` hardcodes `AGNO_HOST=127.0.0.1`, which breaks WSL2 mirrored networking. Change to `0.0.0.0`:
```python
# In pantheon_init.py, inside _start_agno()
env["AGNO_HOST"] = "0.0.0.0"  # was "127.0.0.1"
```

**Verification after patch:**
```bash
# 1. Server bound to all interfaces
ss -tlnp | grep 9120
# Expected: LISTEN 0.0.0.0:9120

# 2. PNA preflight returns 200 with proper headers
curl -s -D - -X OPTIONS \
  -H "Origin: https://os.agno.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Private-Network: true" \
  -H "Access-Control-Request-Headers: content-type,authorization" \
  http://localhost:9120/
# Expected: HTTP/1.1 200 OK
#           access-control-allow-private-network: true
#           access-control-allow-methods: POST
#           access-control-allow-headers: content-type,authorization

# 3. Unknown origin rejected with 403
curl -s -D - -X OPTIONS \
  -H "Origin: https://evil.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Private-Network: true" \
  http://localhost:9120/
# Expected: HTTP/1.1 403 Forbidden

# 4. Regular response has CORS headers
curl -s -D - -H "Origin: https://os.agno.com" http://localhost:9120/
# Expected: access-control-allow-origin: https://os.agno.com
#           access-control-allow-credentials: true
```

## HTTPS Mode for Agno (Mixed Content Fix)

**Pitfall:** Browsers block HTTPS pages (e.g., `os.agno.com`) from calling HTTP APIs (`localhost:9120`). Even with CORS, the mixed-content policy wins. Agno must serve **HTTPS locally**.

### 1. Generate a self-signed certificate

```bash
mkdir -p /mnt/z/pantheon/.agno-certs
cd /mnt/z/pantheon/.agno-certs
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=localhost"
```

### 2. Patch `serve_agno.py` to read cert paths from env

The uvicorn call must include `ssl_keyfile` and `ssl_certfile`:

```python
uvicorn.run(
    app,
    host=host,
    port=port,
    ...,
    ssl_keyfile=os.getenv("AGNO_SSL_KEYFILE"),
    ssl_certfile=os.getenv("AGNO_SSL_CERTFILE"),
)
```

### 3. Start Agno with HTTPS

```bash
export AGNO_SSL_KEYFILE=/mnt/z/pantheon/.agno-certs/key.pem
export AGNO_SSL_CERTFILE=/mnt/z/pantheon/.agno-certs/cert.pem
cd /mnt/z/pantheon/projects/purple-phoenix/main/agent_context/scripts
uv run --active python serve_agno.py
```

### 4. Verify

```bash
# Should return JSON over HTTPS (ignore cert warning with -k)
curl -sk https://127.0.0.1:9120 | python3 -m json.tool
```

Point `os.agno.com` to `https://localhost:9120`.

**Pitfall: Self-signed certs from `openssl` do NOT work for cross-origin fetch().**
Browsers allow you to click "Advanced → Proceed" when visiting `https://localhost:9120` directly in a tab. But when `os.agno.com` (a different HTTPS origin) tries to `fetch()` that same URL, the browser still rejects the self-signed certificate as untrusted. The manual trust click only applies to the current tab's navigation, not to `XMLHttpRequest` / `fetch` from other websites.

**Symptoms:** The Agno control plane shows a "loading..." spinner or connection failure, and the browser console shows `NET::ERR_CERT_AUTHORITY_INVALID`. Directly visiting `https://localhost:9120` in a tab works fine.

**Fix 1: Use mkcert (proper, permanent)**
**Fix 1: Use mkcert (proper, permanent, free tier)**
`mkcert` creates a local CA that your browser trusts automatically, so `fetch()` works without warnings.

On WSL (no sudo available):
```bash
# Install mkcert to ~/.local/bin
mkdir -p ~/.local/bin
curl -sL "https://dl.filippo.io/mkcert/latest?for=linux/amd64" -o ~/.local/bin/mkcert
chmod +x ~/.local/bin/mkcert
export PATH="$HOME/.local/bin:$PATH"

# Generate cert
mkdir -p /mnt/z/pantheon/.agno-certs && cd /mnt/z/pantheon/.agno-certs
mkcert localhost 127.0.0.1 ::1

# Copy root CA to Windows Desktop for manual trust
cp ~/.local/share/mkcert/rootCA.pem "/mnt/c/Users/<username>/Desktop/agno-local-ca.pem"
```

On Windows: double-click the `.pem`, install to **Local Machine** → **Trusted Root Certification Authorities**, then restart the browser.

Start AgentOS with the generated files:
```bash
export AGNO_SSL_KEYFILE=/mnt/z/pantheon/.agno-certs/localhost+2-key.pem
export AGNO_SSL_CERTFILE=/mnt/z/pantheon/.agno-certs/localhost+2.pem
```

**Fix 2: Chrome `--allow-insecure-localhost` (quick workaround, no setup)**
Close all Chrome windows, then open PowerShell and run:
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --allow-insecure-localhost
```
Then open `os.agno.com` and connect to `https://localhost:9120`. This flag tells Chrome to permit self-signed certs on localhost for cross-origin requests.

**Fix 3: Use the Tailscale URL (no cert issue)**
Point `os.agno.com` to `https://<host>.<tailnet>.ts.net/agno` instead of `localhost:9120`. Tailscale already handles HTTPS with valid certificates, so no local cert setup is needed. This is the simplest option if you only need remote access.

**Note:** Tailscale obtains these certificates automatically via `tailscale cert <domain>` — real Let's Encrypt certs, no manual setup.

**WSL localhost forwarding:** WSL2 auto-forwards Windows `localhost:9120` to WSL's `127.0.0.1:9120`, so `https://localhost:9120` from Windows hits the WSL service correctly.

**Note:** `tailscale serve` proxies HTTPS → HTTPS fine; no extra config needed. The Tailscale path `/agno` remains `https://<host>.<tailnet>.ts.net/agno`.

## Dashboard Path Prefix (Tailscale White Screen Fix)

**Pitfall:** `tailscale serve` strips the `/hermes` path prefix when proxying, but does **NOT** inject the `X-Forwarded-Prefix` header that the Hermes dashboard expects. Without this, the SPA serves absolute asset URLs like `/assets/...` instead of `/hermes/assets/...`, causing a white screen (all JS/CSS 404).

**The `HERMES_DASHBOARD_PREFIX` env var exists but the dashboard code only reads the HTTP header**, not the env var. Two fixes are needed:

### Fix 1: Patch `web_server.py` to read the env var

In `hermes_cli/web_server.py`, find the two calls to `_normalise_prefix(request.headers.get("x-forwarded-prefix"))` and change them to:

```python
prefix = _normalise_prefix(
    request.headers.get("x-forwarded-prefix")
    or os.environ.get("HERMES_DASHBOARD_PREFIX", "")
)
```

There are two call sites — one in `serve_css()` and one in `serve_spa()`.

### Fix 2: Always start the dashboard with the env var explicitly set

```bash
HERMES_DASHBOARD_PREFIX=/hermes hermes dashboard --no-open --skip-build --insecure --host 0.0.0.0 --port 9119
```

**Do NOT rely on the env var being inherited from the parent shell** — when started via systemd, tmux, or background processes, the env may be stripped. Pass it explicitly on the command line.

### Verification after fix

```bash
curl -s http://localhost:9119/hermes/ | grep -E 'src=\"|href=\"' | head -3
# Should show: src="/hermes/assets/..." (prefixed), NOT src="/assets/..." (unprefixed)
```

## Agno HTTPS + Tailscale (502 Fix)

**Pitfall:** When Agno serves HTTPS with self-signed certificates (see "HTTPS Mode for Agno" above), Tailscale **must** proxy with `https+insecure://`, not `http://`. Using `http://` causes a 502 because Tailscale speaks HTTP to an HTTPS backend.

### Correct Tailscale configuration

```bash
# WRONG ❌ — causes 502
tailscale serve --bg --https=443 --set-path=/agno http://127.0.0.1:9120

# CORRECT ✅
tailscale serve --bg --https=443 --set-path=/agno https+insecure://127.0.0.1:9120
```

`https+insecure://` tells Tailscale to accept the self-signed certificate instead of validating it.

### Verification

```bash
# Local HTTPS (ignore cert warning)
curl -sk -o /dev/null -w "%{http_code}" https://127.0.0.1:9120/
# Expected: 200

# Via Tailscale (from another device on the tailnet)
curl -sk -o /dev/null -w "%{http_code}" https://<host>.<tailnet>.ts.net/agno/
# Expected: 200
```

After starting all services, run these in sequence:

```bash
# 1. Ports are listening
ss -tlnp | grep -E '9119|6006|9120'

# 2. Dashboard returns HTML
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9119/hermes
# Expected: 200

# 3. Phoenix returns HTML
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:6006
# Expected: 200

# 4. AgentOS returns JSON (HTTP mode)
curl -s http://127.0.0.1:9120 | python3 -m json.tool
# Expected: {"name":"AgentOS API", ...}

# 4a. AgentOS returns JSON (HTTPS mode — mixed-content fix)
curl -sk https://127.0.0.1:9120 | python3 -m json.tool
# Expected: {"name":"AgentOS API", ...}

# 5. Tailscale paths are registered
tailscale serve status | grep -E 'hermes|phoenix|agno'
```

## References

- `references/systemd-auto-start.md` — User-level systemd service for auto-starting Hermes + Phoenix + Tailscale on WSL boot
- `references/phoenix-observability.md` — Phoenix plugin for Hermes: OTel tracing, TRACEPARENT propagation across subprocess boundaries, and dashboard integration
- `references/pna-serve-agno.md` — Complete PNA+CORS patch for `serve_agno.py` when `os.agno.com` free tier must connect to `http://localhost:9120`
- `references/cors-ssl-patch.md` — CORS + SSL code patches for `serve_agno.py` when connecting `os.agno.com` to a local AgentOS instance (HTTPS/mixed-content case)
- `references/agno-agent-os.md` — Agno AgentOS internals, self-hosting, and persistent worker patterns (from `hermes-external-integration` skill)
- `tailscale-serve-localhost` skill — Generic Tailscale serve/reset/status commands
- `hermes-agent` skill — Hermes CLI reference and dashboard configuration

## Notes

- The user prefers a single `pantheon expose start/stop/status` command. The CLI exists but may timeout; manual layer-by-layer startup is the reliable fallback until the command stabilizes.
- Hermes dashboard must be restarted after WSL restarts (systemd services don't persist reliably without `systemd=true` in `/etc/wsl.conf`).
- Phoenix is started automatically by `pantheon expose` but can also be started manually from the Hermes venv: `phoenix serve --host 0.0.0.0 --port 6006`
- The user prefers self-hosted over SaaS options for Agno control plane.

## Browser Loopback Security (PNA)

When serving local services (Hermes dashboard, Phoenix, Agno AgentOS) behind
Tailscale or directly on `localhost`, browsers enforce **Private Network Access (PNA)**
rules that block public origins from fetching loopback addresses.

### Chrome PNA Policy (Chrome 94+)

**The error:**
```
Access to fetch at 'http://localhost:9120/health' from origin 'https://os.agno.com'
has been blocked by CORS policy: Permission was denied for this request to access
the `loopback` address space.
```

**Required server response for PNA preflight:**
```
HTTP/1.1 200 OK
Access-Control-Allow-Private-Network: true
Access-Control-Allow-Origin: https://os.agno.com
Access-Control-Allow-Methods: POST
Access-Control-Allow-Headers: content-type,authorization
```

### FastAPI / Starlette PNA Middleware

Starlette's built-in `CORSMiddleware` intercepts OPTIONS preflight **before**
`BaseHTTPMiddleware`. To add PNA headers, subclass `CORSMiddleware` directly:

```python
from starlette.middleware.cors import CORSMiddleware

class PnaCORSMiddleware(CORSMiddleware):
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "OPTIONS":
            headers = dict(scope.get("headers", []))
            if headers.get(b"access-control-request-private-network") == b"true":
                async def pna_send(message):
                    if message["type"] == "http.response.start":
                        headers = list(message.get("headers", []))
                        headers.append((b"access-control-allow-private-network", b"true"))
                        message["headers"] = headers
                    await send(message)
                await super().__call__(scope, receive, pna_send)
                return
        await super().__call__(scope, receive, send)
```

**Do NOT use `BaseHTTPMiddleware`** for PNA — it buffers response bodies and breaks
SSE streaming from AgentOS.

### Self-Signed Certificates for Local HTTPS

Browsers block HTTPS pages from calling HTTP APIs (mixed content policy). To serve
Agno AgentOS over HTTPS locally:

**Option A: `mkcert` (recommended for cross-origin fetch)**
```bash
mkcert localhost 127.0.0.1 ::1
# Copy rootCA.pem to Windows Desktop and install to Trusted Root CAs
```

**Option B: Chrome `--allow-insecure-localhost` (quick workaround)**
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --allow-insecure-localhost
```

**Option C: Tailscale URL (no cert issue)**
Point `os.agno.com` to `https://<host>.<tailnet>.ts.net/agno` instead of `localhost:9120`.

### WSL2 Binding Pitfall

The server must bind to `0.0.0.0`, NOT `127.0.0.1`, so Windows can reach WSL
services via mirrored networking:

```python
# WRONG
uvicorn.run(app, host="127.0.0.1", port=9120)

# CORRECT
uvicorn.run(app, host="0.0.0.0", port=9120)
```

### Verification Checklist

```bash
# 1. PNA preflight returns 200
curl -s -D - -X OPTIONS \
  -H "Origin: https://os.agno.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Private-Network: true" \
  http://localhost:9120/

# 2. Unknown origin rejected with 403
curl -s -D - -X OPTIONS \
  -H "Origin: https://evil.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Private-Network: true" \
  http://localhost:9120/

# 3. Server bound to all interfaces
ss -tlnp | grep 9120
# Expected: LISTEN 0.0.0.0:9120
```

See `references/browser-loopback-security/pna-fastapi-example.md` for the complete
FastAPI/Starlette PNA middleware implementation.
- The user's Hermes custom plugins (Phoenix observability, ShellCheck security) live on the `znh/custom` branch and should NOT be pushed upstream to NousResearch/hermes-agent.