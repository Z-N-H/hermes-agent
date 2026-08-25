# Server/Client Plugin Architecture (Cross-Machine Tools)

## The Problem

When an Obsidian plugin depends on a server-side CLI tool (ccc, database
access, API keys stored on the server), the default OpenCode approach of
spawning a subprocess with hardcoded paths does not work. Obsidian runs on
a different machine (pop-os-1) while the server-side tooling lives on
bazzite. The plugin cannot reach `/home/znh/.local/bin/ccc` or
`/mnt/z/pantheon/secrets.json` from the device.

## The Pattern: HTTP Bridge

Build a tiny HTTP server on the server-side machine that wraps the tool
and returns JSON. The Obsidian plugin then makes HTTP calls to the bridge
over Tailscale instead of spawning local subprocesses.

```
Obsidian App (pop-os-1)  --HTTPS/Tailscale-->  HTTP Bridge (bazzite:8377)
Plugin calls requestUrl()  <---JSON response--  Wraps ccc + pantheon_query
```

## Component Checklist

### 1. Server-side Bridge (Python, stdlib only)
- Use http.server from stdlib (no FastAPI/Flask dependency)
- Endpoints: GET /search?q=..., GET /health
- Import and reuse existing parser/re-ranker modules from the project
  (e.g. pantheon_search.py) rather than reimplementing parsing
- Inject API keys from gcloud secrets or environment at startup
- Listen on 127.0.0.1 (Tailscale handles external access)
- Return JSON with Content-Type: application/json

### 2. Tailscale Exposure
Register as a path alongside existing services:
```
tailscale serve --bg --set-path /ccc http://127.0.0.1:8377
```
Makes bridge reachable at: https://bazzite.centaur-perch.ts.net/ccc/search?q=...

### 3. Obsidian Plugin Changes
- Remove all child_process.exec() and hardcoded paths (CCC_BIN, SECRETS_FILE, VAULT_DIR)
- Use Obsidian's built-in requestUrl() for HTTP calls (no CORS issues)
- Strip monorepo path prefixes from result paths so clicks resolve correctly
- Add a health check on load to show bridge status in the status bar

### 4. System Integration
- Register bridge as systemd user service with Restart=on-failure
- Add Tailscale path registration to pantheon-stack.sh
- Add health check to pantheon_status.py for the heartbeat dashboard
- After writing plugin files, restart sync daemon: systemctl --user restart ob-headless-sync.service

## Concrete Example (2026-07-29)

The ccc semantic search bridge:

| Component | Before (broken) | After (working) |
|-----------|-----------------|-----------------|
| Plugin | exec(CCC_BIN, ..., {cwd: VAULT_DIR}) — fails on device | requestUrl({url: bridge}) — works over Tailscale |
| Bridge | None | ccc_search_bridge.py on :8377 wraps pantheon_search.py |
| Tailscale | — | serve --set-path /ccc http://127.0.0.1:8377 |
| Systemd | — | pantheon-ccc-search-bridge.service |
| Heartbeat | — | ccc bridge row in pantheon_status.py |

## When To Use This Pattern

Use when ALL are true:
1. Obsidian plugin (or similar client-side integration)
2. Plugin needs CLI tool, database, or secrets file access
3. That tool/filesystem lives on a different machine than Obsidian
4. Machines connected via Tailscale

Do NOT use when:
- Plugin only manipulates vault directory files
- Plugin only uses Obsidian's own APIs
- The server-side tool is also installed on the device
