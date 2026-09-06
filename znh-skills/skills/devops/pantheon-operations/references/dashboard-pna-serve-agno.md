# PNA Patch for serve_agno.py (os.agno.com Free Tier)

When `os.agno.com` free tier connects to `http://localhost:9120`, Chrome's Private Network Access (PNA) policy blocks the request unless the server responds correctly to the PNA preflight.

## The Error

Browser console shows:
```
Access to fetch at 'http://localhost:9120/health' from origin 'https://os.agno.com'
has been blocked by CORS policy: Permission was denied for this request to access
the `loopback` address space.
```

## The Fix (Current — Pure ASGI)

**Do NOT add a second `CORSMiddleware`** — duplicate CORS middlewares produce conflicting `Access-Control-Allow-Origin` headers that Chrome rejects. Instead, pass `cors_allowed_origins` to `AgentOS(...)` and add a thin pure-ASGI PNA middleware.

**Why pure ASGI instead of `BaseHTTPMiddleware`:** `BaseHTTPMiddleware` buffers response bodies to support its `dispatch(self, request, call_next)` pattern. This breaks Server-Sent Events (SSE) streaming from AgentOS. Pure ASGI middleware wraps `send` directly without buffering.

Replace the CORS/PNA section in `_create_app()` in `serve_agno.py`:

```python
agent_os = AgentOS(
    name="HermesAgentOS",
    description="Agno AgentOS with HermesAgent integration.",
    db=db,
    agents=[agent],
    # Let Agno handle standard CORS — merged with Agno's default domains.
    # Do NOT add a second CORSMiddleware on the app; duplicate CORS
    # middleware produces conflicting headers that Chrome rejects.
    cors_allowed_origins=["https://os.agno.com"],
)

app = agent_os.get_app()

# Chrome Private Network Access (PNA): when a public site (os.agno.com)
# fetches from localhost, Chrome sends an extra preflight header
# Access-Control-Request-Private-Network: true and requires the server to
# respond with Access-Control-Allow-Private-Network: true. Agno's built-in
# CORS does not handle this, so we add a thin middleware for it.
#
# Implemented as a pure ASGI middleware (not BaseHTTPMiddleware) to avoid
# buffering response bodies, which would break SSE streaming from AgentOS.
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
        pna_requested = (
            headers.get(b"access-control-request-private-network") == b"true"
        )

        # PNA preflight: only allow origins on the explicit allowlist.
        if method == "OPTIONS" and pna_requested:
            if origin not in _PNA_ALLOWED_ORIGINS:
                # Reject unknown origins — return 403 with no CORS headers.
                await send({
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [],
                })
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
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": resp_headers,
            })
            await send({"type": "http.response.body", "body": b""})
            return

        # Non-preflight: inject PNA header into the response without
        # buffering the body (preserves SSE streaming).
        async def send_with_pna(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"access-control-allow-private-network", b"true"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_pna)


app.add_middleware(PrivateNetworkAccessMiddleware)
```

## Key Differences from Earlier BaseHTTPMiddleware Approach

| Aspect | Old (`BaseHTTPMiddleware`) | New (Pure ASGI) |
|--------|---------------------------|-----------------|
| CORS handling | Manual `CORSMiddleware` added to app | `cors_allowed_origins` passed to `AgentOS` |
| PNA middleware type | `BaseHTTPMiddleware` subclass | Pure ASGI callable class |
| Origin validation | Echoed any origin (with fallback) | Explicit `_PNA_ALLOWED_ORIGINS` allowlist; 403 for unknown |
| SSE streaming | Broken (body buffering) | Works (wraps `send` without buffering) |
| BrowserUI middleware | `BaseHTTPMiddleware` | Also pure ASGI |

## Required Environment

The server must bind to `0.0.0.0` (not `127.0.0.1`) so Windows can reach WSL localhost:

```bash
export AGNO_HOST=0.0.0.0
# unset SSL so it serves HTTP (PNA only applies to HTTP loopback access)
unset AGNO_SSL_CERTFILE AGNO_SSL_KEYFILE
```

**Pitfall in `pantheon_init.py`:** The `_start_agno()` function hardcodes `AGNO_HOST=127.0.0.1`, which breaks WSL2 `networkingMode=Mirrored`. Patch it to `0.0.0.0`.

## Verification

```bash
# 1. Server bound to all interfaces
ss -tlnp | grep 9120
# Expected: LISTEN 0.0.0.0:9120

# 2. PNA preflight returns 200 with echoed headers
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

# 3. Unknown origin rejected
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

## When NOT to Use This

- If using `os.agno.com` Pro with a custom domain/Tailscale URL → just use HTTPS + normal CORS
- If the server is already on a public URL → PNA does not apply
- If using the self-hosted Agno UI only (no os.agno.com) → PNA does not apply
