# `no_agent=true` Runner Pattern — Inbox Scanner Example

## Background

The inbox-scanner cron job needed to send Slack Block Kit messages, but the Hermes cron framework injects a system-level instruction: **"do NOT use send_message or try to deliver the output yourself — your final response will be auto-delivered."** This instruction cannot be overridden at the prompt level — it's in the system prompt assembly.

The workaround: use `no_agent=true` so the cron scheduler runs a Python script (not an LLM session). The script then calls `hermes chat -q` directly, which gives the model full tool access including `send_message` with `blocks`.

## The Runner Script

Path: `/mnt/z/pantheon/.hermes/scripts/inbox_scanner_runner.py`

### Structure

```
1. Run inbox_scanner.py, capture stdout
2. If "NO_ACTION_REQUIRED" in output → exit 0 silently (no tokens, no Slack)
3. Otherwise, build a combined query string:
   - Scanner output as context
   - Full processing prompt (categories, vault mapping, Block Kit templates)
4. Call: hermes chat -q "$query" --quiet --skills obsidian,slack-formatting
5. Suppress hermes chat -q stdout/stderr (→ DEVNULL) to avoid double-delivery
```

### Key Design Decisions

1. **`subprocess.DEVNULL` on both stdout and stderr**: The `hermes chat -q` session uses `send_message` for Slack delivery. With `no_agent=true`, the scheduler also delivers stdout verbatim. Suppressing stdout prevents the message from being delivered twice (once via `send_message`, once via stdout forwarding).

2. **Silent exit on "nothing to do"**: When the scanner finds no new files, the script exits 0 with no stdout. With `no_agent=true`, this means nothing is delivered — no noisy "inbox clear" every 2 minutes.

3. **`--skills obsidian,slack-formatting`**: The `hermes chat -q` session loads these skills so the model knows the vault structure, file paths, and Block Kit formatting templates.

### Cron Config (after the change)

```json
{
  "id": "dd5f55fe34c6",
  "name": "inbox-scanner",
  "script": "inbox_scanner_runner.py",
  "no_agent": true,
  "schedule": { "kind": "interval", "minutes": 2 },
  "deliver": "all"
}
```

### Critical Deployment Step

The running **gateway caches job config at startup**. After updating `jobs.json` to set `no_agent=true` and `script=inbox_scanner_runner.py`, the gateway must be restarted:

```bash
systemctl --user restart pantheon-hermes-gateway
```

Without the restart, the gateway continues using the old config (agent mode with the old prompt) and the runner script is never invoked.

### Session History

- **2026-07-24**: Original cron job created with agent-mode prompt. Block Kit didn't work because of the "do NOT use send_message" restriction.
- **2026-07-24 (later)**: OpenCode created `inbox_scanner_runner.py` and updated `jobs.json` with `no_agent=true`. Config change was written but never activated — gateway needed restart.
- **2026-07-25**: The gateway restart requirement was identified as the root cause of "this is still blocking." This reference file documents the pattern.
