# Private Network Access (PNA) — FastAPI/Starlette Middleware

Complete working middleware from session 2026-06-21 debugging os.agno.com → localhost:9120 connection.

## The Problem

Chrome 94+ blocks public HTTPS websites from accessing `http://localhost` via `fetch()` unless the server responds with `Access-Control-Allow-Private-Network: true` on both OPTIONS preflight and regular responses.

Error seen in browser console:
```
Access to fetch at 'http://localhost:9120/health' from origin 'https://os.agno.com'
has been blocked by CORS policy: Permission was denied for this request to access
the `loopback` address space.
```

## Why Simple Middleware Fails

A `BaseHTTPMiddleware` added AFTER `CORSMiddleware` will **never see OPTIONS requests** because Starlette's `CORSMiddleware` intercepts them first and returns:
```
HTTP/1.1 400 Bad Request
Disallowed CORS private-network
```

The `CORSMiddleware` has built-in logic to reject PNA preflights. You must **subclass `CORSMiddleware`** to bypass this check.

## Working Solution

Two pieces required:
1. A subclassed `CORSMiddleware` that intercepts PNA preflights before the parent rejects them
2. A pure-ASGI wrapper that injects the PNA header into regular responses

```python
from fastapi.middleware.cors import CORSMiddleware

class PnaCORSMiddleware(CORSMiddleware):
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "OPTIONS":
            request_headers = dict(scope.get("headers", []))
            origin = request_headers.get(b"origin", b"").decode("latin-1")
            if origin and b"access-control-request-private-network" in request_headers:
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
    allow_origins=["https://os.agno.com"],  # explicit origin, NOT "*" — Firefox rejects wildcard with credentials
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

## Alternative Approach: Framework Already Handles CORS

When the framework already adds CORS (e.g., Agno AgentOS via `cors_allowed_origins`), use this instead:

```python
    agent_os = AgentOS(
        ...,
        cors_allowed_origins=["https://os.agno.com"],
    )
    app = agent_os.get_app()

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

            async def send_with_pna(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"access-control-allow-private-network", b"true"))
                    message = {**message, "headers": headers}
                await send(message)

            await self.app(scope, receive, send_with_pna)

    app.add_middleware(PrivateNetworkAccessMiddleware)
```

| Approach | When to use |
|----------|------------|
| Subclass CORSMiddleware (above) | Framework does NOT add CORS automatically |
| Framework CORS + Pure ASGI PNA | Framework already adds CORS (e.g., Agno, Django) |

## Verification

```bash
# 1. PNA preflight must return 204, NOT 400
curl -s -D - -X OPTIONS \
  -H "Origin: https://os.agno.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Private-Network: true" \
  http://localhost:9120/health
# Expected:
# HTTP/1.1 204 No Content
# access-control-allow-private-network: true
# access-control-allow-origin: https://os.agno.com

# 2. Regular response must also have the header
curl -s -D - -H "Origin: https://os.agno.com" http://localhost:9120/health
# Expected:
# HTTP/1.1 200 OK
# access-control-allow-private-network: true
# access-control-allow-origin: *
```

## Complete serve_agno.py Snippet

For the specific Agno AgentOS use case, the full patch inside `_create_app()`:

```python
    app = agent_os.get_app()

    from fastapi.middleware.cors import CORSMiddleware

    class PnaCORSMiddleware(CORSMiddleware):
        async def __call__(self, scope, receive, send):
            if scope["type"] == "http" and scope["method"] == "OPTIONS":
                request_headers = dict(scope.get("headers", []))
                origin = request_headers.get(b"origin", b"").decode("latin-1")
                if origin and b"access-control-request-private-network" in request_headers:
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
        allow_origins=["https://os.agno.com"],  # explicit origin, NOT "*" — Firefox rejects wildcard with credentials
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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

## Context

- This is **separate from standard CORS.** The FastAPI `CORSMiddleware` alone does NOT add the PNA header, and it actively **blocks** PNA preflights.
- This is **separate from mixed content blocking.** PNA applies even when both sides are HTTPS. Mixed content only applies to HTTPS→HTTP.
- The `PrivateNetworkAccessMiddleware` must be added **after** `PnaCORSMiddleware` so it wraps all responses.
- **Firefox** enforces `allow_origins=["*"]` + `allow_credentials=True` as a spec violation. Use explicit origins instead.
- **Vivaldi** is Chromium-based and has the same PNA enforcement as Chrome. The `vivaldi://flags` page may not expose PNA controls; use the command-line flag `--disable-features=PrivateNetworkAccessSendPreflights` if needed.
- **Chrome caches PNA preflight results aggressively.** If the server is fixed but Chrome still blocks, try: incognito window, hard-refresh, or a different port (Chrome treats each port as a separate origin).
- **WSL2 binding:** On WSL2 with `networkingMode=Mirrored`, the server must bind to `0.0.0.0`, not `127.0.0.1`, for Windows to reach it via `localhost`. See `wsl-localhost` skill.
- **Duplicate CORSMiddleware produces conflicting headers.** When a framework (e.g., Agno AgentOS) already adds CORS internally via `AgentOS(..., cors_allowed_origins=[...])`, do NOT add a second `CORSMiddleware` on the app. Chrome rejects responses with multiple/conflicting `Access-Control-Allow-Origin` headers. Use the framework's built-in CORS and add only a pure-ASGI PNA middleware. See `pantheon-exposure` skill → `references/pna-serve-agno.md`.

## Related
- `wsl-localhost` skill — if Windows cannot reach WSL localhost at all
- `pantheon-exposure` skill — full Agno AgentOS serving setup
