---
name: browser-loopback-security
description: Diagnose and fix browser security policies that block public HTTPS websites from accessing localhost/loopback services.
version: 1.0.0
---

# Browser Loopback Security

## Trigger Conditions
- A public HTTPS website (e.g. `os.agno.com`) cannot connect to a local HTTP/HTTPS server on `localhost` or `127.0.0.1`
- Browser console shows errors mentioning `loopback`, `CORS policy`, `mixed content`, or `ERR_CERT_AUTHORITY_INVALID`
- Local server is confirmed running and reachable from the same machine

## Key Distinctions

Three separate browser security mechanisms can block this. Check the **exact error** to identify which one:

| Error Pattern | Mechanism | Fix |
|---|---|---|
| `Permission was denied for this request to access the loopback address space` | Chrome/**Vivaldi** **Private Network Access (PNA)** | Server must respond with `Access-Control-Allow-Private-Network: true` |
| `CORS NO Allow Credentials` or similar (Firefox) | Firefox rejects `allow_origins=["*"]` when `allow_credentials=True` | Use explicit origin list instead of wildcard |
| `Mixed Content: The page at ... was loaded over HTTPS, but requested an insecure resource` | **Mixed Content** blocking | Serve localhost over HTTPS, or use Chrome `--allow-insecure-localhost` |
| `NET::ERR_CERT_AUTHORITY_INVALID` | Self-signed cert rejected | Install local CA, or use `--allow-insecure-localhost` |
| CORS error without `loopback` mention | Standard **CORS** | Add `Access-Control-Allow-Origin: *` and other CORS headers |
| `ERR_CONNECTION_REFUSED` or timeout to `localhost:PORT` | Stale process on a different port, or server bound to `127.0.0.1` only | Check for old processes (`ps aux | grep serve_agno`), verify binding is `0.0.0.0` |

## 0. Stale Process Cleanup (check first)

Before diagnosing browser security policies, verify the server you think is running is actually the one on the expected port. Old processes from previous sessions can linger on adjacent ports and confuse debugging.

```bash
# Check for ANY process matching your server
ps aux | grep serve_agno | grep -v grep
# If multiple processes appear, kill the old ones and keep only the current one.

# Verify the port binding
ss -tlnp | grep <port>
# Should show: LISTEN 0.0.0.0:<port>  (NOT 127.0.0.1:<port>)
```

**Pitfall:** On WSL2 with `networkingMode=Mirrored`, a server bound to `127.0.0.1` is reachable from inside WSL but NOT from Windows via `localhost`. Windows `localhost` only reaches WSL when the server binds `0.0.0.0`. See `wsl-localhost` skill.

## 1. Private Network Access (PNA) — Chrome 94+

Chrome blocks public HTTPS origins from accessing `localhost` unless the server explicitly opts in.

**Error:**
```
Access to fetch at 'http://localhost:9120/...' from origin 'https://os.agno.com'
has been blocked by CORS policy: Permission was denied for this request to access
the `loopback` address space.
```

**Why the simple middleware doesn't work:**
Starlette's `CORSMiddleware` intercepts OPTIONS requests **before** custom middleware runs, and it actively rejects PNA preflights with a 400 `Disallowed CORS private-network` error. A `BaseHTTPMiddleware` added after `CORSMiddleware` never sees the OPTIONS request.

**Correct fix for FastAPI/Starlette:**
Subclass `CORSMiddleware` to intercept PNA preflights, then add a pure-ASGI wrapper for regular responses:

```python
from fastapi.middleware.cors import CORSMiddleware

class PnaCORSMiddleware(CORSMiddleware):
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "OPTIONS":
            request_headers = dict(scope.get("headers", []))
            origin = request_headers.get(b"origin", b"").decode("latin-1")
            if origin and b"access-control-request-private-network" in request_headers:
                # PNA preflight — bypass parent CORSMiddleware rejection
                response_headers = [
                    (b"access-control-allow-origin", origin.encode("latin-1")),
                    (b"access-control-allow-private-network", b"true"),
                    (b"access-control-allow-methods", b"*"),
                    (b"access-control-allow-headers", b"*"),
                    (b"access-control-allow-credentials", b"true"),
                ]
                await send({
                    "type": "http.response.start",
                    "status": 204,
                    "headers": response_headers,
                })
                await send({"type": "http.response.body", "body": b""})
                return
        await super().__call__(scope, receive, send)

app.add_middleware(
    PnaCORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Also inject PNA header into regular (non-preflight) responses
class PrivateNetworkAccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_pna(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append(
                    (b"access-control-allow-private-network", b"true")
                )
                message = dict(message)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_pna)

app.add_middleware(PrivateNetworkAccessMiddleware)
```

**Verification:**
```bash
# PNA preflight must return 204, not 400
curl -s -D - -X OPTIONS \
  -H "Origin: https://os.agno.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Private-Network: true" \
  http://localhost:9120/health
# Expected: HTTP/1.1 204 No Content
#           access-control-allow-private-network: true

# Regular response must also have the header
curl -s -D - -H "Origin: https://os.agno.com" http://localhost:9120/health
# Expected: access-control-allow-private-network: true
```

### Alternative: Framework Already Handles CORS (e.g. Agno AgentOS)

When the web framework already adds `CORSMiddleware` internally (e.g., `AgentOS(..., cors_allowed_origins=[...])`), adding a second `CORSMiddleware` on the app produces **conflicting `Access-Control-Allow-Origin` headers** that Chrome rejects.

**Do NOT subclass `CORSMiddleware` in this case.** Instead:
1. Let the framework handle CORS via its built-in config
2. Add only a thin pure-ASGI PNA middleware for the PNA preflight

```python
    # Framework handles CORS — pass origins to its constructor
    agent_os = AgentOS(
        ...,
        cors_allowed_origins=["https://os.agno.com"],
    )
    app = agent_os.get_app()

    # Add pure-ASGI PNA middleware (NOT BaseHTTPMiddleware — it buffers
    # response bodies and breaks SSE streaming).
    _PNA_ALLOWED_ORIGINS = frozenset({"https://os.agno.com"})

    class PrivateNetworkAccessMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            headers = dict(scope.get("headers", []))
            method = scope.get("method", "")
            origin = (headers.get(b"origin") or b"").decode("latin-1")
            pna_requested = headers.get(b"access-control-request-private-network") == b"true"

            # PNA preflight: validate origin against explicit allowlist.
            if method == "OPTIONS" and pna_requested:
                if origin not in _PNA_ALLOWED_ORIGINS:
                    await send({"type": "http.response.start", "status": 403, "headers": []})
                    await send({"type": "http.response.body", "body": b""})
                    return

                raw_method = headers.get(b"access-control-request-method") or b"GET"
                raw_headers = headers.get(b"access-control-request-headers") or b""
                req_method = raw_method.decode("latin-1")
                req_headers = raw_headers.decode("latin-1")
                resp_headers = [
                    (b"access-control-allow-private-network", b"true"),
                    (b"access-control-allow-origin", origin.encode("latin-1")),
                    (b"access-control-allow-methods", req_method.encode("latin-1")),
                    (b"access-control-allow-headers", req_headers.encode("latin-1")),
                    (b"access-control-allow-credentials", b"true"),
                ]
                await send({"type": "http.response.start", "status": 200, "headers": resp_headers})
                await send({"type": "http.response.body", "body": b""})
                return

            # Non-preflight: inject PNA header into response without buffering.
            async def send_with_pna(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"access-control-allow-private-network", b"true"))
                    message = {**message, "headers": headers}
                await send(message)

            await self.app(scope, receive, send_with_pna)

    app.add_middleware(PrivateNetworkAccessMiddleware)
```

**Key differences from the subclassing approach:**
| Aspect | Subclass `CORSMiddleware` | Framework CORS + Pure ASGI PNA |
|--------|---------------------------|-------------------------------|
| Use when | Framework does NOT add CORS | Framework already adds CORS |
| CORS handling | Manual middleware | Framework built-in config |
| PNA middleware type | Pure ASGI | Pure ASGI |
| Origin validation | Echoes any origin (with fallback) | Explicit allowlist; 403 for unknown |
| SSE streaming | Works | Works |

See `pantheon-exposure` skill → `references/pna-serve-agno.md` for the complete Agno-specific code.

## 2. Mixed Content Blocking

When a page is loaded over HTTPS, the browser blocks fetches to HTTP URLs.

**Error:**
```
Mixed Content: The page at 'https://os.agno.com/...' was loaded over HTTPS,
but requested an insecure resource 'http://localhost:9120/...'.
```

**Fixes:**
1. **Serve localhost over HTTPS** with a self-signed cert (browser will warn, but allows)
2. **Launch Chrome with `--allow-insecure-localhost`** to relax cert checks for localhost
3. **Use `mkcert`** to generate a locally-trusted cert for `localhost`
4. **Pay for the service's Pro tier** to use a custom domain (Tailscale URL with real cert)

## 3. Self-Signed Certificate Rejection

Even with HTTPS, browsers reject self-signed certs for cross-origin requests.

**Error:**
```
NET::ERR_CERT_AUTHORITY_INVALID
```

**Fixes:**
1. **mkcert** — generates a real cert trusted by the system CA store
2. **Chrome flag** — `chrome.exe --allow-insecure-localhost`
3. **Install the CA** — copy the root CA cert to Windows and install into "Trusted Root Certification Authorities"

## Diagnostic Flow

When a public site cannot connect to localhost, follow this order:

1. **Is the server running and bound to 0.0.0.0?**
   ```bash
   ss -tlnp | grep <port>  # should show 0.0.0.0:<port>, not 127.0.0.1:<port>
   ```
   If bound to `127.0.0.1` only and WSL2 with `networkingMode=Mirrored`, see `wsl-localhost` skill.

2. **Is the server reachable from the browser machine?**
   ```powershell
   curl http://localhost:<port>/health
   ```

3. **Check browser console for the exact error** (F12 → Console). Do not guess the mechanism — the error text tells you which policy is blocking.

4. **If the error mentions "loopback address space", verify the server handles PNA correctly:**
   ```bash
   curl -s -D - -X OPTIONS \
     -H "Origin: https://os.agno.com" \
     -H "Access-Control-Request-Method: GET" \
     -H "Access-Control-Request-Private-Network: true" \
     http://localhost:<port>/health
   ```
   - **HTTP 204** with `access-control-allow-private-network: true` → PNA is correct, check other policies
   - **HTTP 400** with `Disallowed CORS private-network` → Starlette CORSMiddleware is blocking PNA. Apply the subclass fix above.

5. **If PNA headers are correct but Chrome still blocks:** Chrome caches preflight results aggressively. Try:
   - **Incognito window** (doesn't share PNA cache)
   - **Hard-refresh** (Ctrl+Shift+R)
   - **Different port** — change the server to `localhost:9121`. Chrome treats each port as a separate origin, so a failed preflight on `:9120` won't affect `:9121`. This is the fastest way to rule out a cached preflight.

6. **Apply the fix matching the exact error** from the table above.

6. **Apply the fix matching the exact error** from the table above.

## Pitfalls

- **Firefox rejects `allow_origins=["*"]` with `allow_credentials=True`.** When using the PNA middleware with credentials enabled, use an explicit origin list like `["https://os.agno.com"]` instead of `["*"]`. Firefox enforces the CORS spec rule that wildcard and credentials are incompatible.
- **Do not confuse PNA with CORS.** Standard CORS headers alone do NOT satisfy PNA. The `Access-Control-Allow-Private-Network` header is required separately.
- **Do not confuse PNA with mixed content.** PNA applies even when both origins use HTTPS. Mixed content only applies to HTTPS→HTTP.
- **WSL2 `networkingMode=Mirrored` requires binding to `0.0.0.0`.** If bound to `127.0.0.1`, Windows `localhost` won't reach it at all. See `wsl-localhost` skill.
- **Self-signed certs work for direct navigation but NOT for cross-origin `fetch()`.** The browser allows clicking "Advanced → Proceed" for direct visits, but blocks the same cert silently for `fetch()` from another origin.
- **A 400 Bad Request on the OPTIONS preflight means the server rejected the PNA request.** Check for `Disallowed CORS private-network` in the response body. This means the `CORSMiddleware` is blocking PNA — you must subclass it. See the corrected PNA fix above.
- **Duplicate CORSMiddleware produces conflicting headers.** When a framework (e.g., Agno AgentOS) already adds CORS internally via `AgentOS(..., cors_allowed_origins=[...])`, do NOT add a second `CORSMiddleware` on the app. Chrome rejects responses with multiple/conflicting `Access-Control-Allow-Origin` headers. Use the framework's built-in CORS and add only a pure-ASGI PNA middleware.
- **Stale processes on adjacent ports confuse debugging.** If `serve_agno.py` was restarted but an old instance is still running on `:9121`, the browser may still be cached to `:9120` or the new instance may not be the one serving. Always `ps aux | grep serve_agno` and `ss -tlnp | grep 9120` before diagnosing CORS/PNA issues.

## References
- `references/pna-fastapi-example.md` — complete working PNA+CORS middleware (subclass approach) with verification commands
- `pantheon-exposure` skill → `references/pna-serve-agno.md` — specific patch for Agno AgentOS `serve_agno.py`
- `references/chrome-pna-docs.md` — condensed notes from Chrome PNA documentation