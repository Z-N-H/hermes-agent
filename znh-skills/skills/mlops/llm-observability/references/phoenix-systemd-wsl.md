# Phoenix + Hermes Systemd Auto-Start on WSL

Session: 2026-06-26 — Rolling Phoenix collector + Hermes dashboard into a single systemd user service that starts automatically when WSL2 boots.

## The Problem

Phoenix's `strawberry` + `pydantic` imports are **extremely slow** on WSL's drvfs-mounted filesystems (e.g. `/mnt/z`). Cold-start can take **60–90 seconds** before the HTTP port is listening. A naive systemd `Type=simple` service exits immediately after forking, leaving systemd with no way to know if Phoenix actually came up.

## The Solution

A single shell script (`pantheon-stack.sh`) that starts both services, waits for their ports, and registers Tailscale paths. Managed by a systemd `Type=oneshot` user service with a long `TimeoutStartSec`.

### Script: `pantheon-stack.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_DIR="/mnt/z/pantheon/.hermes/hermes-agent"
PHOENIX_PORT="${PHOENIX_PORT:-6006}"
HERMES_PORT="${HERMES_PORT:-9119}"
LOG_DIR="${HOME}/.local/share/pantheon-stack"
mkdir -p "$LOG_DIR"

_log() {
    echo "[$(date -Iseconds)] $*" | tee -a "$LOG_DIR/pantheon-stack.log"
}

_pid_file() {
    echo "$LOG_DIR/$1.pid"
}

_is_port_open() {
    local port=$1
    timeout 2 bash -c "cat < /dev/null > /dev/tcp/127.0.0.1/$port" 2>/dev/null
}

_wait_for_port() {
    local port=$1
    local name=$2
    local max_wait=$3
    local waited=0

    _log "Waiting for $name on port $port (max ${max_wait}s)..."
    while ! _is_port_open "$port"; do
        sleep 2
        waited=$((waited + 2))
        if [[ $waited -ge $max_wait ]]; then
            _log "ERROR: $name failed to start on port $port within ${max_wait}s"
            return 1
        fi
    done
    _log "$name ready on port $port (waited ${waited}s)"
}

_start_phoenix() {
    if _is_port_open "$PHOENIX_PORT"; then
        _log "Phoenix already running on port $PHOENIX_PORT"
        return 0
    fi

    _log "Starting Phoenix on port $PHOENIX_PORT..."
    cd "$HERMES_DIR"
    source venv/bin/activate

    export PHOENIX_HOST=0.0.0.0
    export PHOENIX_PORT=$PHOENIX_PORT
    export PHOENIX_HOST_ROOT_PATH=/phoenix

    nohup phoenix serve \
        --host 0.0.0.0 \
        --port "$PHOENIX_PORT" \
        > "$LOG_DIR/phoenix.log" 2>&1 &
    local pid=$!
    echo "$pid" > "$(_pid_file phoenix)"
    _log "Phoenix launched (PID $pid)"

    # Phoenix can take 60-90s to start on WSL drvfs
    _wait_for_port "$PHOENIX_PORT" "Phoenix" 120 || return 1
}

_start_hermes_dashboard() {
    if _is_port_open "$HERMES_PORT"; then
        _log "Hermes dashboard already running on port $HERMES_PORT"
        return 0
    fi

    _log "Starting Hermes dashboard on port $HERMES_PORT..."
    cd "$HERMES_DIR"
    source venv/bin/activate

    export HERMES_DASHBOARD_PREFIX=/hermes

    nohup hermes dashboard \
        --no-open \
        --skip-build \
        --insecure \
        --host 0.0.0.0 \
        --port "$HERMES_PORT" \
        > "$LOG_DIR/hermes-dashboard.log" 2>&1 &
    local pid=$!
    echo "$pid" > "$(_pid_file hermes-dashboard)"
    _log "Hermes dashboard launched (PID $pid)"

    _wait_for_port "$HERMES_PORT" "Hermes dashboard" 30 || return 1
}

_register_tailscale() {
    if ! command -v tailscale &> /dev/null; then
        _log "Tailscale not found — skipping path registration"
        return 0
    fi

    _log "Checking Tailscale paths..."
    local status
    status=$(tailscale serve status 2>/dev/null || true)

    if ! echo "$status" | grep -q "/hermes"; then
        tailscale serve --bg --set-path /hermes "http://127.0.0.1:$HERMES_PORT" || true
    fi

    if ! echo "$status" | grep -q "/phoenix"; then
        tailscale serve --bg --set-path /phoenix "http://127.0.0.1:$PHOENIX_PORT" || true
    fi

    _log "Tailscale paths registered"
}

_stop_service() {
    local name=$1
    local pidfile
    pidfile="$(_pid_file "$name")"

    if [[ -f "$pidfile" ]]; then
        local pid
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            sleep 2
            kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$pidfile"
    fi
}

start() {
    _log "=== Starting Pantheon Stack ==="
    _start_phoenix
    _start_hermes_dashboard
    _register_tailscale
    _log "=== Pantheon Stack started ==="
}

stop() {
    _log "=== Stopping Pantheon Stack ==="
    _stop_service "phoenix"
    _stop_service "hermes-dashboard"
    _log "=== Pantheon Stack stopped ==="
}

status() {
    echo "=== Pantheon Stack Status ==="
    if _is_port_open "$PHOENIX_PORT"; then echo "Phoenix: RUNNING"; else echo "Phoenix: STOPPED"; fi
    if _is_port_open "$HERMES_PORT"; then echo "Hermes:  RUNNING"; else echo "Hermes:  STOPPED"; fi
}

case "${1:-start}" in
    start) start ;;
    stop) stop ;;
    status) status ;;
    restart) stop; sleep 2; start ;;
    *) echo "Usage: pantheon-stack {start|stop|status|restart}"; exit 1 ;;
esac
```

### Systemd user service

```ini
# ~/.config/systemd/user/pantheon-stack.service
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
SyslogIdentifier=pantheon-stack
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/home/znh/.local/bin"
Environment="HOME=/home/znh"

[Install]
WantedBy=default.target
```

### Why `Type=oneshot`

- `simple` exits immediately after forking → systemd marks active even if Phoenix hasn't started
- `oneshot` waits for the script to finish → systemd only marks active after port validation succeeds
- `TimeoutStartSec=180` gives Phoenix its full 120s startup budget plus margin
- `RemainAfterExit=yes` keeps the service in "active" state after the script exits

### Enable and start

```bash
chmod +x /mnt/z/pantheon/vault/ZNH/scripts/pantheon-stack.sh
systemctl --user daemon-reload
systemctl --user enable pantheon-stack.service
systemctl --user start pantheon-stack.service
systemctl --user status pantheon-stack.service --no-pager
```

## Tailscale paths

The script registers:
- `/hermes` → `http://127.0.0.1:9119`
- `/phoenix` → `http://127.0.0.1:6006`

Access at `https://{tailscale-domain}/phoenix` and `https://{tailscale-domain}/hermes`.

## Key insight: WSL drvfs is the bottleneck

Phoenix imports `strawberry` → `pydantic` → many small `.py` files. On a native Linux filesystem this is fast. On WSL's `/mnt/z` (9P/drvfs) each `import` stat/open/read is a cross-boundary syscall and can take 60–90 seconds total. Plan for this — do not assume startup timeouts measured on native Linux apply to WSL.

## Files from this session

- `/mnt/z/pantheon/vault/ZNH/scripts/pantheon-stack.sh` — unified startup script
- `/home/znh/.config/systemd/user/pantheon-stack.service` — systemd user service
