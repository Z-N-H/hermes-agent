---
name: wsl-localhost
description: Troubleshoot and fix localhost forwarding from Windows to WSL2 servers.
version: 1.0.0
---

# WSL2 Localhost Forwarding

## Trigger Conditions
- Server is running inside WSL2 but not reachable from Windows via `localhost` or `127.0.0.1`
- WSL2 is configured with `networkingMode=Mirrored` in `.wslconfig`
- Port appears to be listening (`ss -tlnp` shows it) but Windows `curl http://localhost:<port>` hangs or fails

## Diagnosis

1. Check the server is actually listening:
   ```bash
   ss -tlnp | grep <port>
   ```

2. Check what interface it bound to:
   - `127.0.0.1:<port>` = only reachable from WSL itself
   - `0.0.0.0:<port>` = reachable from Windows (if WSL networking is working)

3. Test from inside WSL:
   ```bash
   curl http://localhost:<port>
   ```

4. Test from Windows PowerShell:
   ```powershell
   curl http://localhost:<port>
   ```

## The Fix

WSL2 with `networkingMode=Mirrored` does **not** reliably forward Windows `localhost` to WSL processes that bind to `127.0.0.1`. The server must explicitly bind to `0.0.0.0` (all interfaces).

### For Python/uvicorn/FastAPI:
Set the host to `0.0.0.0`:
```python
uvicorn.run(app, host="0.0.0.0", port=9120)
```
Or via environment variable before starting the script:
```bash
export AGNO_HOST=0.0.0.0
python serve_agno.py
```

### For Node.js:
```javascript
server.listen(3000, '0.0.0.0');
```

### Generic pattern:
When a server in WSL2 is not reachable from Windows via `localhost`, change the bind address from `127.0.0.1` to `0.0.0.0`.

## Verification
After binding to `0.0.0.0`:
```bash
ss -tlnp | grep <port>
# Should show: LISTEN 0.0.0.0:<port>
```

Then test from Windows:
```powershell
curl http://localhost:<port>
```

## Follow-Up Issues
After localhost forwarding works, a public HTTPS website (e.g. `os.agno.com`) may still fail to connect. Check browser console (F12 → Console) for:
- **"Permission was denied for this request to access the `loopback` address space"** → Chrome Private Network Access (PNA) blocking. See `browser-loopback-security` skill.
- **"Mixed Content"** → HTTPS page trying to fetch HTTP localhost. See `browser-loopback-security` skill.
- **CORS errors** → Missing CORS headers on the server.

These are browser security policies, not WSL networking issues.

## When It Does Not Apply
- Native Windows servers (not in WSL)
- WSL1 (uses different networking architecture)
- Servers already bound to `0.0.0.0`
- Issues resolved by restarting WSL (`wsl --shutdown`)

## Pantheon-Specific Pitfall

Pantheon's `_start_agno()` function hardcodes `AGNO_HOST=127.0.0.1`, which silently breaks WSL2 localhost forwarding. See `references/pantheon-agno-host-pitfall.md` for the exact line, the patch, and why the env var workaround doesn't help.

## References
- `references/wsl-localhost-forwarding.md` — session-specific troubleshooting details
- `references/pantheon-agno-host-pitfall.md` — Pantheon `_start_agno()` hardcoded `127.0.0.1` issue
- `references/drvfs-filesystem-access.md` — drvfs root-level permission denied on `/mnt/<drive>` while subdirs remain accessible