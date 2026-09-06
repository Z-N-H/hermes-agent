---
name: wsl-environment
description: "WSL2 operational patterns — filesystem quirks, localhost forwarding, networking, and interoperability with Windows."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, windows]
metadata:
  hermes:
    tags: [wsl, windows, filesystem, networking, localhost, devops]
---

# WSL Environment

## Overview

WSL2 is the primary deployment target for Pantheon and Hermes in this environment. It has
specific filesystem, networking, and process-lifecycle quirks that repeatedly block workflows.
This skill covers the two dominant failure modes: filesystem/drvfs issues and localhost
forwarding/binding issues.

## When to Use

- File permission problems under `/mnt/c/` or `/mnt/z/`
- Git operations failing with permission or inotify errors
- `localhost` not reaching a WSL-bound service from Windows
- Confusion about `127.0.0.1` vs `0.0.0.0` binding under WSL2 mirrored networking
- Service startup timing out because of slow drvfs imports

## Filesystem & drvfs

### Permission model

`/mnt/c/` and `/mnt/z/` use the 9P/drvfs protocol. Permissions are emulated:

```bash
# Files created from Windows get 777 + no x-bit
chmod +x script.sh        # works inside WSL
# But Windows-side creation ignores umask
```

**Git pitfall:** `git clone` on drvfs may produce files with wrong executable bits,
causing `pre-commit` hooks or shebang scripts to fail silently.

**Fix:** Clone repos to the WSL native filesystem (`/home/<user>/...`) when possible.
Use `/mnt/` only for cross-OS file sharing.

### inotify limitations

`watchdog` and `inotify` on drvfs are unreliable or silently fail:

- `PollingObserver` is the fallback but can deadlock on long-lived systemd services
- File-change events may not fire; processes appear "active" but produce zero output
- **Detection:** `journalctl --user -u <service> --since today` shows no `[WATCH]` entries
  even after modifying files
- **Fix:** Restart the service (`systemctl --user restart <service>`); add `flush=True`
  to startup prints for earlier detection

See `references/filesystem/drvfs-permissions.md` for exact permission mappings.
See `references/filesystem/inotify-drvfs-limitation.md` for the watchdog deadlock
reproduction and mitigation.
See `references/filesystem/tmp-and-git-permissions.md` for git-on-drvfs recipes.

## Localhost Forwarding & Binding

### WSL2 `networkingMode=Mirrored`

With mirrored networking, Windows `localhost` should reach WSL services. The catch:
**services must bind to `0.0.0.0`, NOT `127.0.0.1`**.

```bash
# WRONG — Windows cannot reach this
uvicorn.run(app, host="127.0.0.1", port=9120)

# CORRECT
uvicorn.run(app, host="0.0.0.0", port=9120)
```

### Verification checklist

```bash
# 1. Server bound to all interfaces
ss -tlnp | grep <port>
# Expected: LISTEN 0.0.0.0:<port>

# 2. Windows can reach it
curl http://localhost:<port>

# 3. WSL can reach it
curl http://127.0.0.1:<port>
```

### Self-signed certificates on WSL

`os.agno.com` and similar services need HTTPS locally. `openssl` self-signed certs
work for direct tab navigation but NOT for cross-origin `fetch()` from other HTTPS
origins. Use `mkcert` instead:

```bash
mkcert localhost 127.0.0.1 ::1
```

Copy `rootCA.pem` to Windows Desktop and install to **Trusted Root Certification Authorities**.

See `references/localhost/drvfs-filesystem-access.md` for cross-OS path mapping.
See `references/localhost/pantheon-agno-host-pitfall.md` for the `127.0.0.1` vs `0.0.0.0`
binding pitfall in Pantheon's `_start_agno()`.
See `references/localhost/wsl-localhost-forwarding.md` for the full port-forwarding matrix.

## Multiprocessing / Semaphore Permission Denied

Python's `multiprocessing` module (used by crawlee, playwright, and many data-processing
libraries) creates semaphores in `/dev/shm`. On WSL2, `/dev/shm` sometimes has wrong
permissions, causing:

```
PermissionError: [Errno 13] Permission denied
  File ".../multiprocessing/synchronize.py", line 169, in __init__
    SemLock.__init__(self, SEMAPHORE, 1, 1, ctx=ctx)
```

**Symptoms:**
- Crawlee/playwright scrapers fail with `requests_failed=5`, `unique_errors=1`
- Background workers or parallel agents crash on startup
- `0 pages scraped` even though URLs are reachable

**Fixes (in order of preference):**
1. **Run without multiprocessing** — set `single_process=True` or use the synchronous
   crawler path if the library supports it.
2. **Fix `/dev/shm` permissions** — `sudo chmod 1777 /dev/shm` (temporary, resets on WSL restart).
3. **Use WSL native filesystem** — move the working directory to `/home/<user>/...`
   instead of `/mnt/z/...`; semaphore creation is more reliable on native ext4.
4. **WSL config** — add to `/etc/wsl.conf` and restart WSL:
   ```ini
   [boot]
   systemd=true
   ```

## Systemd & Service Lifecycles on WSL

WSL does not persist systemd services across restarts unless `systemd=true` is set in
`/etc/wsl.conf`. After a WSL restart, manually started services (dashboard, Phoenix,
trigger scanner) must be restarted.

**Pitfall:** `systemctl --user is-active <service>` may report `active` while the
underlying `watchdog` observer has silently stopped dispatching events. Always verify
by checking logs (`journalctl`) or by triggering a test event.
