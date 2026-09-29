# Pantheon-Specific WSL Localhost Pitfall

## The Issue

In Pantheon's `agent_context/scripts/pantheon_init.py`, the `_start_agno()` function hardcodes `AGNO_HOST=127.0.0.1` when launching the Agno AgentOS server:

```python
# Line ~2544 in pantheon_init.py
def _start_agno() -> bool:
    ...
    env = os.environ.copy()
    env["AGNO_PORT"] = str(agno_port)
    env["AGNO_HOST"] = "127.0.0.1"  # ← breaks WSL2 mirrored networking
    subprocess.Popen(
        [python_bin, str(serve_script)],
        ...,
        env=env,
    )
```

This breaks `networkingMode=Mirrored` on WSL2 because Windows `localhost` cannot reach WSL processes bound to `127.0.0.1`. The server must bind to `0.0.0.0`.

## The Patch

Change one line in `pantheon_init.py`:

```python
env["AGNO_HOST"] = "0.0.0.0"  # was "127.0.0.1"
```

Then reinstall the tool:
```bash
cd /mnt/z/pantheon/.pantheon
uv tool install -e .
```

## Why This Keeps Reverting

The `_start_agno()` function is in the main `pantheon_init.py` script, not in `serve_agno.py`. When `pantheon expose start` runs, it spawns `serve_agno.py` via `subprocess.Popen` with `AGNO_HOST` set in the environment. The `serve_agno.py` script reads this via `os.getenv("AGNO_HOST", "127.0.0.1")`, so the hardcoded value in `pantheon_init.py` always wins.

Even if you set `AGNO_HOST=0.0.0.0` in your shell before running `pantheon expose start`, the `_start_agno()` function overwrites it with its own hardcoded value.

## Verification After Patch

```bash
# 1. Kill any running Agno process
pantheon expose stop
# or: ss -tlnp | grep 9120 → note PID → kill <PID>

# 2. Restart
pantheon expose start --no-tailscale

# 3. Verify binding
ss -tlnp | grep 9120
# Expected: LISTEN 0.0.0.0:9120  (NOT 127.0.0.1:9120)
```

## Related

- `pantheon-exposure` skill — full dashboard stack documentation
- `wsl-localhost` skill — general WSL2 localhost forwarding troubleshooting
