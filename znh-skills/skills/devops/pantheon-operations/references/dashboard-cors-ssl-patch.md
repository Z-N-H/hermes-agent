# CORS + SSL Patch for serve_agno.py

When exposing the Agno AgentOS API to a hosted HTTPS frontend (e.g., `os.agno.com`), two things are required:
1. **CORS middleware** so cross-origin requests are allowed.
2. **HTTPS serving** so the browser's mixed-content policy doesn't block the API.

## Patch 1: CORS Middleware

Insert this block immediately after `app = agent_os.get_app()` in `serve_agno.py`:

```python
    app = agent_os.get_app()

    # Add CORS so the hosted Agno studio (os.agno.com) can connect
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # os.agno.com + any local dev origin
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

## Patch 2: SSL Certificate Support

Update the `uvicorn.run()` call in `main()` to read cert paths from environment variables:

```python
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=log_level,
        reload=reload,
        access_log=True,
        ssl_keyfile=os.getenv("AGNO_SSL_KEYFILE"),
        ssl_certfile=os.getenv("AGNO_SSL_CERTFILE"),
    )
```

When `AGNO_SSL_KEYFILE` and `AGNO_SSL_CERTFILE` are set, uvicorn serves HTTPS. When unset, it falls back to HTTP.

## Quick Start (HTTPS)

```bash
# 1. Generate a self-signed cert (once)
mkdir -p /mnt/z/pantheon/.agno-certs
cd /mnt/z/pantheon/.agno-certs
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=localhost"

# 2. Export paths
export AGNO_SSL_KEYFILE=/mnt/z/pantheon/.agno-certs/key.pem
export AGNO_SSL_CERTFILE=/mnt/z/pantheon/.agno-certs/cert.pem

# 3. Start Agno
cd /mnt/z/pantheon/projects/purple-phoenix/main/agent_context/scripts
uv run --active python serve_agno.py

# 4. Verify HTTPS
curl -sk https://127.0.0.1:9120 | python3 -m json.tool
```

## Verification with Headers

To confirm CORS headers are present:

```bash
curl -sk -D - -o /dev/null -H "Origin: https://os.agno.com" https://127.0.0.1:9120/
# Expect: access-control-allow-origin: *
```

---

## Self-Signed Cert Limitation for Cross-Origin fetch()

The `openssl` self-signed cert recipe above works for:
- Direct browser navigation to `https://localhost:9120`
- `curl -k` / `curl --insecure`
- Tailscale `https+insecure://` proxying

It does **NOT** work for:
- `fetch()` / `XMLHttpRequest` from a hosted HTTPS site like `os.agno.com`
- Cross-origin API calls where the browser enforces certificate validation

Browsers treat manually trusted self-signed certs as valid only for the tab that clicked "Proceed". Other origins still see `NET::ERR_CERT_AUTHORITY_INVALID`.

## mkcert: Proper Localhost HTTPS

For a cert that works everywhere (including cross-origin fetch from hosted UIs):

```bash
# Install mkcert
sudo apt install mkcert libnss3-tools   # Debian/Ubuntu
# or: brew install mkcert              # macOS

# Create and install local CA
mkcert -install

# Generate cert for localhost
mkcert -cert-file /mnt/z/pantheon/.agno-certs/cert.pem -key-file /mnt/z/pantheon/.agno-certs/key.pem localhost 127.0.0.1 ::1

# Export and start Agno
export AGNO_SSL_KEYFILE=/mnt/z/pantheon/.agno-certs/key.pem
export AGNO_SSL_CERTFILE=/mnt/z/pantheon/.agno-certs/cert.pem
uv run --active python serve_agno.py
```

`mkcert` creates a certificate authority that browsers trust automatically. No "Advanced → Proceed" needed, and cross-origin `fetch()` works without flags.

## Chrome Workaround

If you can't install `mkcert` immediately, start Chrome with:
```powershell
chrome.exe --allow-insecure-localhost
```
This permits self-signed localhost certs for cross-origin requests during that browser session.
