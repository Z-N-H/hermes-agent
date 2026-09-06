---
name: cron-operations
description: Manage Hermes cron jobs — creation, scheduling, troubleshooting, and the critical gateway-dependency pitfall. Use when a cron job doesn't fire, needs debugging, or when setting up recurring automation.
version: 1.1.0
platforms: [linux, macos]
environments: [hermes]
metadata:
  hermes:
    tags: [cron, scheduler, operations, gateway]
    related_skills: [obsidian, opencode-worker]
---

# Hermes Cron Operations

## Critical Dependency: Gateway Must Be Running

**Cron jobs will NOT fire unless the Hermes gateway is running.** This is the #1 cause of "job is configured but doesn't run."

To check:
```bash
hermes cron status
```

Output when gateway is **down**:
```
✗ Gateway is not running — cron jobs will NOT fire

  To enable automatic execution:
    hermes gateway install    # Install as a user service
    sudo hermes gateway install --system  # Linux servers: boot-time system service
    hermes gateway            # Or run in foreground
```

Output when gateway is **running**:
```
✓ Gateway is running
```

## Checking Job Status

```bash
# List all jobs with next/last run times and health
hermes cron list

# Check gateway + cron health in one command
hermes cron status
```

**What to look for in the list output:**
- `last_run_at` is `null` → job has **never** fired (likely gateway issue, or newly created)
- `last_status` is `error` → script or LLM phase failed
- `state: paused` → job was manually paused, not dead

## Testing Jobs Without Running the Gateway

Use `tick` mode — runs all due jobs once and exits, no gateway required:

```bash
hermes cron tick
```

This is the safest way to test a new or modified job without starting the full gateway daemon.

## The `no_agent=true` Mode

### What it is

By default, cron jobs run as full LLM agent sessions — the scheduler injects a system prompt (including any loaded skills), calls the model, and auto-delivers the model's response. In this mode, the model receives a system-level instruction: **"do NOT use send_message or try to deliver the output yourself"** — the response is auto-delivered.

Setting `no_agent=true` changes the behaviour entirely:
- The scheduler runs the script (via `script` field) and captures stdout verbatim
- No LLM is involved at the cron level
- Stdout is delivered as-is to the configured target
- No "do NOT use send_message" restriction (there's no LLM session to restrict)

### When to use it

Use `no_agent=true` when:

1. **The LLM needs full tool access** (especially `send_message` with `blocks`) — the cron framework's "don't use send_message" instruction can't be overridden at the prompt level. The only way to give the model `send_message` access is to remove the cron framework from the LLM path entirely.

2. **The script itself produces the final deliverable** — no LLM processing needed, just raw stdout forwarded to Slack/Telegram.

3. **Token cost reduction** — if the data-collection script can determine "nothing to do" before invoking the LLM, you save every tick's token spend on empty cycles.

### The Runner Script Pattern

This is the most common `no_agent=true` workflow:

```
Cron scheduler (no_agent=true)
         ↓ runs script
Runner Python script
    ├── 1. Run data-collection script, capture stdout
    ├── 2. If "nothing to do" → exit 0 silently (no delivery)
    └── 3. If there's work → call `hermes chat -q` with processing prompt
              ↓
         Full LLM session (NO "do NOT use send_message" restriction)
              ↓
         Model uses send_message blocks → rich Slack/Telegram output
```

**Key details:**
- The runner script calls `hermes chat -q --skills <skills>` to give the LLM tool access
- Inside `hermes chat -q`, the model CAN call `send_message` with `blocks` — no framework restriction
- The script suppresses `hermes chat -q` stdout/stderr (to DEVNULL) to avoid double-delivery since the LLM already delivered via `send_message`
- The script must handle errors gracefully since the cron scheduler has no LLM fallback

### Delivery model with `no_agent=true`

| Script stdout | What gets delivered |
|--------------|-------------------|
| Nothing (empty or suppressed) | Nothing delivered — the LLM inside handled delivery via `send_message` |
| Text content | Delivered verbatim to configured targets |
| Exit code 0 + empty stdout | Silent — no delivery (use for "nothing to do" short-circuit) |
| Exit code non-zero | Error logged in `last_status`, delivery depends on script output |

### Verifying `no_agent=true` is active

Check the cron output file at `.hermes/cron/output/<job-id>/<timestamp>.md`:

- **Agent-processed** (default): File starts with `# Cron Job: <name>`, has `## Prompt` and `## Response` sections, ~80-90KB
- **`no_agent=true`**: File is just the raw script stdout, no headers/prompt sections, much smaller (or empty if stdout was suppressed)

## Common Pitfalls

### 1. Job configured but never fires — gateway isn't running
As above. `hermes cron status` is the first diagnostic.

### 2. (MOVED) Config changes don't take effect — gateway caches job config at startup
**ROOT CAUSE:** The gateway (systemd service `pantheon-hermes-gateway.service`) reads `jobs.json` ONCE at startup and caches everything — schedule, prompt, script, `no_agent`, skills, deliver target, `context_from`. Changes made via `cronjob action=update` write to `jobs.json` but the running gateway never re-reads the file.

**Diagnostic pattern:** Check the cron output file format:
- **Agent-processed output** (default mode, config change NOT picked up): The output starts with `# Cron Job: <name>`, has `## Prompt` (full skill content), and `## Response` sections. Files are ~80-90KB.
- **`no_agent=true` raw stdout** (config change WAS picked up): The output is just the script's stdout — no headers, no prompt section, much smaller.

If the output still has the structured agent-processed format, the gateway is using the OLD config.

**Fix:** Restart the gateway:
```bash
systemctl --user restart pantheon-hermes-gateway
```
This is a ~5-second restart. All jobs lose one tick, then resume from the updated config.

**Verification after restart:** Wait one tick cycle, then check the output file format matches the expected mode (raw stdout for `no_agent=true`, structured for agent mode).

**This affects ALL config changes:** schedule, prompt, script, no_agent, skills, deliver, context_from, paused state, model override — everything.

### 4. (PREVIOUSLY 3) Data-collection script resolves wrong paths
Cron job scripts using `Path(__file__).resolve().parent.parent` for path resolution will break when the script lives in `.hermes/scripts/` and expects to be in a different directory tree. Always hardcode critical paths or make them configurable via environment variables.

**Diagnostic:** Run the script manually:
```bash
python3 .hermes/scripts/<your-script>.py
```
If it reports 0 files or wrong directories, the path resolution is wrong.

**Fix:** Replace relative path resolution with an absolute path:
```python
# BROKEN (moved to .hermes/scripts/):
VAULT = Path(__file__).resolve().parent.parent

# FIXED:
VAULT = Path("/absolute/path/to/your/vault")
```

### 5. Script succeeds but LLM phase produces no output
The cron pipeline has two phases:
1. **Data collection** (the `.py` script) — stdout becomes context for the LLM
2. **LLM processing** (the prompt + loaded skills) — generates the deliverable message

If the script outputs `NO_ACTION_REQUIRED`, the LLM phase still runs but has nothing to act on. If the LLM doesn't produce meaningful output, the job may complete silently. Check `last_delivery_error` in `hermes cron list` for hints.

### 6. WSL: OpenCode / Bun path issues
If your cron job delegates to OpenCode, see the `wsl-environment` and `opencode-worker` skills for WSL-specific pitfalls (symlinks pointing to `.exe`, musl/glibc mismatches, `/tmp` permission issues).

### 7. Schedule format confusion
`hermes cron` accepts human-readable schedules:
- `every 30m` — every 30 minutes
- `every 2h` — every 2 hours
- `every 1m` — every minute (for testing only)
- `0 9 * * *` — cron standard format (daily at 9am)
- ISO timestamp — one-shot

**Pitfall:** `every 1m` is valid but will fire every 60 seconds. Dial back to `every 30m` or `every 1h` after testing. The LLM agent processing each tick costs tokens.

### 8. Background script invocation
The cron job system runs scripts in a headless environment. The script cannot assume a TTY, interactive input, or a specific working directory. Scripts must be fully self-contained — no `input()`, no GUI, no interactive prompts.

### 9. MCP initialization fails on every tick (non-fatal)
The gateway log may show:
```
WARNING cron.scheduler: Job '<id>': MCP initialization failed (non-fatal): 'function' object is not subscriptable
```
This warning appears when the cron scheduler attempts to initialise MCP tools for the agent session. It is **non-fatal** — the job continues to run. The root cause is an internal scheduler issue with tool initialisation order. This does not affect output or delivery. Ignore unless it's accompanied by actual job failures.

## Quick Start: Creating a New Cron Job

```bash
hermes cron create \
  --name "my-scanner" \
  --schedule "every 30m" \
  --prompt "Process the data from my-script.py output and..." \
  --script my-script.py \
  --skills "obsidian,slack-formatting" \
  --deliver "all"
```

Parameters:
- `--script <name>` — path under `.hermes/scripts/<name>` (relative) or absolute path
- `--skills` — comma-separated skill names loaded before the prompt
- `--deliver "all"` — deliver to every connected channel
- `--deliver "local"` — save only, no delivery

## Updating Existing Jobs

```bash
# Change schedule
hermes cron update <job-id> --schedule "every 1h"

# Pause/resume without deleting
hermes cron pause <job-id>
hermes cron resume <job-id>

# Force run on next tick (or test with `tick`)
hermes cron run <job-id>

# Full config change
hermes cron edit <job-id>
```
