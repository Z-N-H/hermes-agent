# Systemd Auto-Start for Pantheon Stack

User-level systemd service that auto-starts Hermes dashboard + Phoenix + Tailscale paths whenever WSL2 comes online.

## Why User-Level (Not System)

WSL2 does not support `systemd` system services well. Use `--user` services instead:

```bash
systemctl --user enable pantheon-stack.service
systemctl --user start pantheon-stack.service
```

Requires `systemd=true` in `/etc/wsl.conf`:
```ini
[boot]
systemd=true
```

## Service File

Location: `~/.config/systemd/user/pantheon-stack.service`

```ini
[Unit]
Description=Pantheon Stack — Hermes dashboard + Phoenix + Tailscale
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/mnt/z/pantheon/vault/ZNH/scripts/pantheon-stack.sh start
ExecStop=/mnt/z/pantheon/vault/ZNH/scripts/pantheon-stack.sh stop
RemainAfterExit=yes
TimeoutStartSec=180
TimeoutStopSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

**Why `Type=oneshot` (not `simple`)**: Phoenix can take **60–90 seconds** to start on WSL's `/mnt/z` drvfs because `strawberry` + `pydantic` imports are extremely slow over 9P. `Type=oneshot` lets systemd wait for the start script to finish before marking the service active. `TimeoutStartSec=180` gives Phoenix enough time.

**Why `RemainAfterExit=yes`**: The script forks background processes (`nohup`) and exits. Without this, systemd would mark the service as dead immediately.

**No `Restart=on-failure`**: `oneshot` services do not support restart. If Phoenix crashes after startup, use `systemctl --user restart pantheon-stack.service` manually.

## Start Script

Location: `/mnt/z/pantheon/vault/ZNH/scripts/pantheon-stack.sh`

Key design decisions:
- **Port-wait loops are REQUIRED** — Phoenix binds to port 6006 only after ~24s of imports on drvfs. The script must poll the port before proceeding to start Hermes.
- **PID files** — write `phoenix.pid` and `hermes-dashboard.pid` to `~/.local/share/pantheon-stack/` so `ExecStop` can reliably find and kill the correct processes.
- **Env vars explicitly passed** — `HERMES_DASHBOARD_PREFIX=/hermes` must be set in the script, not inherited from parent shell.

### `_wait_for_port()` helper

```bash
_wait_for_port() {
    local port=$1
    local name=$2
    local max_wait=$3
    local waited=0

    while ! timeout 2 bash -c "cat < /dev/null > /dev/tcp/127.0.0.1/$port" 2>/dev/null; do
        sleep 2
        waited=$((waited + 2))
        if [[ $waited -ge $max_wait ]]; then
            echo "ERROR: $name failed to start on port $port within ${max_wait}s"
            return 1
        fi
    done
}
```

Usage in `_start_phoenix()`:
```bash
nohup phoenix serve --host 0.0.0.0 --port "$PHOENIX_PORT" > "$LOG_DIR/phoenix.log" 2>&1 &
echo "$!" > "$LOG_DIR/phoenix.pid"
_wait_for_port "$PHOENIX_PORT" "Phoenix" 120 || return 1
```

### `_stop_service()` helper (reads PID files)

```bash
_stop_service() {
    local name=$1
    local pidfile="$LOG_DIR/$name.pid"
    if [[ -f "$pidfile" ]]; then
        local pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            sleep 2
            kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$pidfile"
    fi
}
```

### Pitfall: Missing env vars in systemd context

When started via systemd, the service gets a minimal environment. Always set critical env vars inside the script:
```bash
export HERMES_DASHBOARD_PREFIX=/hermes
export PHOENIX_HOST=0.0.0.0
export PHOENIX_HOST_ROOT_PATH=/phoenix
```

### Pitfall: `source venv/bin/activate` inside scripts

Works fine in bash scripts but the venv path must be absolute:
```bash
cd /mnt/z/pantheon/.hermes/hermes-agent
source venv/bin/activate
```

## Commands

```bash
# Start now
systemctl --user start pantheon-stack.service

# Check status
systemctl --user status pantheon-stack.service

# View logs
journalctl --user -u pantheon-stack.service -f

# Restart
systemctl --user restart pantheon-stack.service

# Stop
systemctl --user stop pantheon-stack.service

# Enable auto-start on boot
systemctl --user enable pantheon-stack.service

# Disable auto-start
systemctl --user disable pantheon-stack.service
```

## Logs

Log directory: `~/.local/share/pantheon-stack/`
- `phoenix.log` — Phoenix stdout/stderr
- `hermes-dashboard.log` — Hermes dashboard stdout/stderr
- `pantheon-stack.log` — Wrapper script actions with timestamps
