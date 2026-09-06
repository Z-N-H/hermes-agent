---
name: pantheon-operations
description: Operate, monitor, and troubleshoot Pantheon services — Hermes cron, Hindsight memory, dashboard/exposure stack, and Pantheon-registered project workflows. Use for service health checks, restart sequences, cron job management, and project operations.
version: 1.1.0
platforms: [linux]
environments: [hermes]
metadata:
  hermes:
    tags: [pantheon, operations, devops, cron, hindsight, dashboard, tailscale, agno, phoenix, project]
---

# Pantheon Operations

Umbrella skill for operating Pantheon services. Each section covers a distinct service or subsystem; refer to the subsection relevant to your current task.

---

## 1. Hermes Cron Operations

### Critical Dependency: Gateway Must Be Running

Cron jobs will NOT fire unless the Hermes gateway is running. Check with:

```bash
hermes cron status
```

Output when gateway is **down**:
```
✗ Gateway is not running — cron jobs will NOT fire
```

### Checking Job Status

```bash
hermes cron list               # All jobs with next/last run times
hermes cron status              # Gateway + cron combined health
```

**What to look for in the list output:**
- `last_run_at` is `null` → job has never fired (likely gateway issue)
- `last_status` is `error` → script or LLM phase failed
- `state: paused` → manually paused

### Testing Without the Gateway

```bash
hermes cron tick                # Runs all due jobs once and exits
```

### The `no_agent=true` Mode

Setting `no_agent=true` on a cron job runs the script alone — no LLM involved at the cron level. Stdout is delivered verbatim. Use this when:

- The LLM needs full `send_message` access (cron's "don't use send_message" restriction doesn't apply in this mode)
- The script itself produces the final deliverable
- You want to save tokens on empty-cycle checks

**Runner script pattern:** The script calls `hermes chat -q` internally when there's actual work. On success, the script produces empty stdout (cron stays silent); Slack delivery happens via `send_message` inside the agent session. On failure, the script prints error details to stdout so cron delivers the failure report.

See `references/cron-no-agent-runner-pattern.md` for the full implementation. The current runner is `scripts/inbox_scanner_runner.py` under this skill.

### Creating a New Cron Job

Use `hermes cron create` for LLM-powered cron jobs, or `no_agent=true` for script-only runners:

```bash
# LLM-powered cron job
hermes cron create \
  --name "my-processor" \
  --schedule "every 30m" \
  --prompt "Process the data..." \
  --skills "obsidian,vault-lookup-by-uid" \
  --deliver "all"

# Script-only runner (no_agent=true) — script calls hermes chat -q internally
hermes cron create \
  --name "inbox-scanner" \
  --schedule "every 30m" \
  --no_agent true \
  --script inbox_scanner_runner.py \
  --deliver local \
  --workdir /mnt/z/pantheon
```

See `scripts/inbox_scanner_runner.py` under this skill for the real implementation of the no_agent runner pattern.

### Updating / Managing Jobs

```bash
hermes cron update <job-id> --schedule "every 1h"
hermes cron pause <job-id>
hermes cron resume <job-id>
hermes cron run <job-id>        # Force run on next tick
```

### Common Pitfalls

1. **Job configured but never fires** — gateway isn't running. `hermes cron status` first.
2. **Config changes don't take effect** — gateway caches `jobs.json` at startup. Restart: `systemctl --user restart pantheon-hermes-gateway`.
3. **Schedule format confusion** — `every 30m`, `every 2h`, `0 9 * * *`, ISO timestamps all valid.
4. **Script path resolution** — scripts using `Path(__file__).resolve().parent` break when the script lives in `.hermes/scripts/`. Hardcode absolute paths.
5. **MCP init warning (non-fatal)** — `MCP initialization failed (non-fatal): 'function' object is not subscriptable` in gateway log is harmless.
6. **WSL: OpenCode/Bun path issues** — symlinks to `.exe`, musl/glibc mismatches in cron context.

### Verifying a Job Actually Ran

The most reliable check that a cron job fired is watching `Next run` in `hermes cron list`:

```bash
# 1. List jobs — note the Next run timestamp
hermes cron list

# 2. Manually trigger the job
hermes cron run <job-id-or-name>

# 3. Wait for a scheduler tick (interval=60s by default), then check again
sleep 65
hermes cron list | grep -A8 "Name:.*<job-name>"
```

**If `Next run` moved forward (e.g. from 10:00 → 22:00), the job ran successfully.** If it stayed the same, the ticker didn't fire.

#### Gateway Log Inspection

The cron ticker is embedded in the Hermes gateway. Check its lifecycle:

```bash
tail -100 /mnt/z/pantheon/.hermes/logs/gateway.log | grep -i "cron\|tick\|job\|librarian"
```

Look for:
- `Cron ticker started (interval=60s)` — ticker is active
- `Cron ticker stopped` — gateway restarted or crashed (check surrounding context)
- Job-specific output — some jobs log completion messages

**Stale heartbeat files:** The files `ticker_heartbeat` and `ticker_last_success` under `.hermes/cron/` are from a previous cron implementation. The current gateway manages ticks in-memory and does NOT update these files. Ignore them.

#### Direct Script Test

For script-based cron jobs, bypass the scheduler entirely:

```bash
cd /mnt/z/pantheon
python3 /mnt/z/pantheon/.hermes/scripts/<script_name>.py [--dry-run]
```

Many vault scripts support `--dry-run` for safe verification.

#### Common Pitfalls

1. **`hermes cron tick` may time out** — if it hangs past 30s, don't retry. Just queue the job with `hermes cron run` and wait for the next 60s tick cycle.
2. **Gateway restarted recently** — check the log for recent `Cron ticker started` entries. If the post-restart ticker started less than 60s ago, jobs haven't had a tick cycle yet.
3. **Job fires but produces no output** — that's correct for no-agent scripts or jobs with empty stdout. Check `hermes cron list` for `last_run_at` to confirm it fired.
4. **`hermes cron status` says gateway is running but jobs don't fire** — the gateway process may be alive but the ticker coroutine crashed silently. Restart the gateway: `systemctl --user restart pantheon-hermes-gateway.service`.

See `references/cron-job-verification.md` for a full walkthrough with real output patterns.

### When to Use Hermes Cron vs Systemd Timer

For vault maintenance scripts that do not need LLM reasoning, prefer a **systemd timer** over a Hermes cron job:

| Criterion | Hermes Cron | Systemd Timer |
|-----------|-------------|---------------|
| Script only (stdout) | Works | **Preferred** — no token cost |
| LLM reasoning needed | **Required** | Not possible |
| Gateway dependency | Yes (cron won't fire without gateway) | No |
| Scheduling precision | ±60s (ticker cycle) | ±0s (systemd timer) |
| Logging | Cron's own output delivery | `journalctl --user -u <service>` |

**Migration pattern:** When a script-based job outgrows Hermes cron — or was always a pure-script job — create a systemd timer+service pair, remove the cron job, and enable the timer. The `--no-retriage` flag pattern lets the script do safe automated work (filing, uid repairs) while gating agent-driven side effects (card creation, ClickUp tasks, Slack messages) behind explicit user approval.

```bash
# One-time setup
systemctl --user enable --now vault-librarian.timer

# Verify
systemctl --user status vault-librarian.timer

# Clean up old Hermes cron
hermes cron remove <old-job-id>
```

See `references/vault-librarian-systemd-timer.md` for the full vault-librarian deployment with systemd unit definitions and verification pattern.

**Combined pattern:** For inbox processing and other recurring vault work, the best architecture uses **both** layers — a systemd timer for mechanical work (filing, move tracking, discard guard) and a Hermes cron `no_agent=true` runner for LLM-intensive work (classification, card creation, Slack summaries). See `references/vault-processing-two-layer-architecture.md` for the full design.

### References

- Full inbox-scanner cron design: `references/cron-session-example-inbox-scanner.md`
- `no_agent=true` runner script implementation: `references/cron-no-agent-runner-pattern.md`
- Cron job verification walkthrough (including ticker state diagnosis): `references/cron-job-verification.md`
- Systemd timer alternative for vault maintenance scripts: `references/vault-librarian-systemd-timer.md`
- Two-layer vault processing (systemd + cron combined): `references/vault-processing-two-layer-architecture.md`

---

## 2. Hindsight Memory Service

### Service Health Check

```bash
systemctl --user status pantheon-hindsight.service
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8888/health
```

Expected: `active (running)` + HTTP 200.

### Fact Extraction Failures

**Symptom:** `hindsight_retain` returns HTTP 500 with `"Fact extraction failed: 1/1 chunks failed"`.

**Root cause:** The LLM model configured for Hindsight's `retain_extract_facts` scope is no longer available at the provider. The real error is in the server log:

```bash
tail -50 /mnt/z/pantheon/.hermes/logs/hindsight-server.log
```

Look for lines like:
```
APIStatusError (openai/hf:..., scope=retain_extract_facts, attempt 1/4): HTTP 404: ... is no longer supported.
```

**Fix:** Update Hindsight config to use an available model, then restart: `systemctl --user restart pantheon-hindsight.service`.

See `references/hindsight-model-deprecation-minimax-m3.md` for the full deprecation diagnosis.

### Recall Failures

Check: (1) Is the service running? (2) Database healthy? (3) Bank name correct (default: `hermes`)?

### Pitfalls

- **API 500 does not mean the service is down.** Health endpoint may return 200 while fact extraction fails due to model issues. Always check the server log.
- **Model deprecation is silent.** Hindsight won't warn. Retain calls just start failing while recall still works (vector search, not LLM extraction).
- **Fact extraction uses a different model than your session.** Changing your chat model does not fix a broken extraction model.

---

## 3. Pantheon Dashboard / Exposure Stack

Manages the four-layer local serving stack for Hermes, Phoenix, and Agno via Tailscale:

1. **Hermes dashboard** on port 9119 (path `/hermes`)
2. **Phoenix observability** on port 6006 (path `/phoenix`)
3. **Agno AgentOS** on port 9120 (path `/agno`)
4. **Tailscale serve** — proxies all three to `https://<host>.<tailnet>.ts.net/...`

### Status Check

```bash
pantheon expose status
# Or manually:
ss -tlnp | grep -E '9119|6006|9120'
tailscale serve status | grep -E 'hermes|phoenix|agno'
```

### Layer 1: Hermes Dashboard (port 9119)

```bash
HERMES_DASHBOARD_PREFIX=/hermes hermes dashboard --no-open --skip-build --insecure --host 0.0.0.0 --port 9119
```

**Pitfall:** There is NO `run` subcommand — it's `hermes dashboard ...` directly.

**Path prefix fix:** Set `HERMES_DASHBOARD_PREFIX=/hermes` env var so asset URLs are prefixed (prevents white screen behind Tailscale). The dashboard code reads `x-forwarded-prefix` header first then falls back to the env var.

### Layer 2: Phoenix Observability (port 6006)

Started via `pantheon expose` or manually:
```bash
phoenix serve --host 0.0.0.0 --port 6006
```

Pre-existing Phoenix instances on port 6006 are auto-detected by `pantheon expose` and skipped.

**Troubleshooting:**
- Phoenix fails to start — `anthropic` version conflict. Fix: `uv pip install --python venv/bin/python 'anthropic>=0.40.0'`
- Slow first startup (60–90s on WSL drvfs) — normal, `strawberry` + `pydantic` imports are slow on network filesystems
- Systemd startup — use `Type=oneshot` with `TimeoutStartSec=180` (not `Type=simple`)

### Layer 3: Agno AgentOS (port 9120)

```bash
cd /mnt/z/pantheon/projects/purple-phoenix/main/agent_context/scripts
uv run --active python serve_agno.py
```

**Pitfall:** The script is NOT at the project root — full path under `projects/purple-phoenix/main/agent_context/scripts/`.

**Dependencies:** Install `uv pip install 'agno[os]'` in the project root.

**WSL2 binding:** Must bind to `0.0.0.0`, not `127.0.0.1`. Patch `pantheon_init.py` or set `AGNO_HOST=0.0.0.0`.

**PNA (Private Network Access):** Chrome blocks HTTPS origins from fetching `http://localhost:9120`. The fix is pure-ASGI middleware (not `BaseHTTPMiddleware`, which breaks SSE). Origin validation against an allowlist; unknown origins get 403. See `references/dashboard-pna-serve-agno.md`.

**HTTPS mode for mixed content:** When `os.agno.com` free tier must connect to local AgentOS:
- Option A: `mkcert` (proper CA, works cross-origin)
- Option B: Chrome `--allow-insecure-localhost` (quick workaround)
- Option C: Point to Tailscale URL `https://<host>.<tailnet>.ts.net/agno` (no cert issue)

See `references/dashboard-cors-ssl-patch.md` for code patches.

### Layer 4: Tailscale Path Registration

```bash
tailscale serve --bg http://127.0.0.1:9119 /hermes
tailscale serve --bg http://127.0.0.1:6006 /phoenix
tailscale serve --bg http://127.0.0.1:9120 /agno
```

When Agno uses HTTPS (self-signed certs), use `https+insecure://` instead of `http://`.

### Quick Verification (after starting all services)

```bash
ss -tlnp | grep -E '9119|6006|9120'
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9119/hermes  # 200
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:6006         # 200
curl -s http://127.0.0.1:9120 | python3 -m json.tool                 # {"name":"AgentOS API",...}
tailscale serve status | grep -E 'hermes|phoenix|agno'
```

### Dashboard Path Prefix (White Screen Fix)

Tailscale strips the `/hermes` prefix and does NOT inject `X-Forwarded-Prefix`. The `HERMES_DASHBOARD_PREFIX` env var is the fix. Two patches needed:

1. Patch `web_server.py` to read the env var as fallback
2. Always start with `HERMES_DASHBOARD_PREFIX=/hermes` explicitly

### References

- Systemd auto-start: `references/dashboard-systemd-auto-start.md`
- Phoenix observability plugin: `references/dashboard-phoenix-observability.md`
- PNA + CORS for Agno: `references/dashboard-pna-serve-agno.md`
- CORS + SSL patches: `references/dashboard-cors-ssl-patch.md`
- Security plugin: `references/dashboard-security-plugin.md`

---

## 4. Project Operations — Topaz-Thoth (Blog Generation)

Topaz-Thoth (Nabu newsroom) is a Pantheon-registered project for generating SEO-optimised blog articles via a multi-agent critique loop.

### Project Location

```bash
/mnt/z/pantheon/projects/topaz-thoth/main/
```

### CLI Reference

The entry point uses `uv`, never bare `python`:

```bash
cd /mnt/z/pantheon/projects/topaz-thoth/main
uv run uown-blog blog "<topic>" \
  --locale <us|uk|au|ca> \
  --client <client_id> \
  --article-type <ALTERNATIVES> \
  --notes "<context>"
```

**Example:**
```bash
uv run uown-blog blog "Achievers alternatives" \
  --locale us --client thankbox --article-type ALTERNATIVES \
  --notes "Focus on US HR managers."
```

Output: `storage/<client>/output/posts/<timestamp>_<slug>.md`

### Client Management

- List clients: `ls storage/`
- Each client needs `storage/<id>/brand_soul.toml`
- New clients: write `brand_souls/<id>.toml`, run `uv run python create_client.py`

### Known Issues

1. **Gemini model deprecation** — `nabu/config.py` and `gemini_client.py` hardcode model names that Google retires periodically. Update both files when seeing 404 errors. See `references/topaz-gemini-model-ids.md`.

2. **Secret loading** — only uses GCP Secret Manager. Patch `_get_secret()` to check env vars first (`LLM_API_KEY`, `DATAFORSEO_API_KEY`, `HELICONE_API_KEY`). See `references/topaz-secret-loading-env-fallback.md`.

3. **WSL2 multiprocessing** — Crawlee spawns Playwright processes via `multiprocessing`. On WSL2 this fails with semaphore permission errors. Pipeline completes with model knowledge only.

4. **DataForSEO optional** — if unavailable, intelligence layer falls back to Tavily or model knowledge.

### Workflow Overview

1. Research Phase (Reddit context, SERP facts)
2. Outline Phase (structured ArticleOutline)
3. Draft Phase (writer agent)
4. Review Loop (3 critics × 5 iterations max)
5. Final Polish (brand voice gloss)
6. Output (markdown to client directory)

### Quick Verification

```bash
cd /mnt/z/pantheon/projects/topaz-thoth/main
uv run python -c "from nabu.config import get_llm_api_key; print('LLM key:', 'OK' if get_llm_api_key() else 'MISSING')"
```

---

## 5. Hermes Update — Custom Branch Workflow

This user manages Hermes via a **git checkout at `/mnt/z/pantheon/.hermes/hermes-agent/`** on the `znh/custom` branch, which carries local commits on top of upstream `main`. **Never run bare `hermes update` on this checkout** — it switches to `main`, installs **main's** dependency pins into `venv/`, and on a successful update never switches back, leaving the venv pinned against the wrong branch (this broke every MCP tool call in the live gateway on 2026-08-22; see also the 2026-07-31 shallow-clone incident).

### Full Update Sequence (automated)

```bash
# 1. Commit any dirty changes on znh/custom (the wrapper refuses a dirty tree)
cd /mnt/z/pantheon/.hermes/hermes-agent
git add -u
git commit -m "chore: working tree changes before upstream sync"

# 2. Run the wrapper — it handles the rest end to end:
/mnt/z/pantheon/.hermes/scripts/safe_hermes_update.sh
```

The wrapper: checks out `main`, runs `hermes update --yes`, returns to
`znh/custom` no matter the outcome (EXIT trap), rebases your commits onto the
fresh `main`, re-syncs `znh/custom`'s `pyproject.toml` pins into **both
`venv/` (what `pantheon-hermes-gateway.service` runs from) and `.venv/` (uv's
default project env — both exist and can silently diverge; keep both
synced)**, verifies the installed `mcp` version matches the pin, runs the
customization guard, and restarts + log-checks the gateway. On a rebase
conflict it stops with instructions — resolve, then re-run it.

### Manual Sequence (only if the wrapper's rebase conflicts and you want a merge)

```bash
git checkout znh/custom
git merge main -m "chore: merge upstream main into znh/custom"

# Resolve conflicts — for files the user explicitly customized
#    (prompt_builder.py, system_prompt.py, etc.), prefer our side.
#    For everything else, accept upstream. See conflict resolution notes below.
git mergetool   # or manual resolution
git commit     # (already staged if --no-edit or -m was used)

# CRITICAL after any manual branch dance: re-sync BOTH venvs from
# znh/custom's pyproject, then restart:
cd /mnt/z/pantheon/.hermes/hermes-agent
VIRTUAL_ENV=$PWD/venv  uv pip install -e '.[all]'
VIRTUAL_ENV=$PWD/.venv uv pip install -e '.[all]'
systemctl --user restart pantheon-hermes-gateway.service

# Verify
hermes --version
systemctl --user status pantheon-hermes-gateway.service | grep "Active"
```

### Conflict Resolution Strategy

The merge often hits 10-15 conflicts after a major version jump. Resolution approach:

- **Files the user explicitly customized** (see `git log znh/custom --oneline --not main` for the list):
  - `agent/prompt_builder.py` — CRITICAL_BOUNDARY_GUIDANCE constant
  - `agent/system_prompt.py` — system prompt customisations
  - `agent/agent_init.py` — Phoenix session tracking
  - `cron/scheduler.py` — custom scheduling
  - `hermes_cli/gateway.py` — gateway tweaks
  - `plugins/memory/hindsight/__init__.py` — memory config
  - `plugins/observability/phoenix/__init__.py`
  - `tools/process_registry.py`
  
  For these, review each conflict: if upstream has a genuine improvement (new features, better patterns), accept theirs. If it's a customization-specific conflict, keep ours. Default: accept upstream for non-customized sections within these files.

- **Files NOT in our commit list** — accept upstream (`git checkout --theirs <file>`)

- **Removed files** (e.g. `gateway/platforms/slack.py` moved to plugin) — accept upstream's deletion

- **`package-lock.json`** — accept upstream's version (always regenerated anyway)

### Pre-Update Checklist

- [ ] Dirty changes committed on `znh/custom`
- [ ] `HERMES_UPDATE_BRANCH` NOT set in `.env` (let update handle `main`)
- [ ] Gateway is running (not needed for update, but useful to have current version noted)

### Post-Update Verification

- [ ] `hermes --version` shows the new version (e.g. v0.19.1)
- [ ] `git log --oneline znh/custom ^main` — your custom commits are still present
- [ ] CRITICAL_BOUNDARY_GUIDANCE intact: `grep -c "CRITICAL_BOUNDARY_GUIDANCE" agent/prompt_builder.py`
- [ ] Gateway restart: `systemctl --user status pantheon-hermes-gateway.service | grep Active`
- [ ] Config migration: `hermes config migrate` (if update didn't auto-run it)
- [ ] Git status clean: `git status --short` shows only expected untracked files (e.g. `bun.lockb`)

---

## 6. Inbox Processing (Two-Layer Architecture)
The vault inbox is processed by two complementary layers:

### Layer 1 — vault-librarian (systemd timer)

**Mechanical work** — move tracking, filing done/discarded notes, discard guard, re-triage of stale un-triaged notes (max 5/run, 2 concurrent), parked nudge after 48h.

- Timer: `~/.config/systemd/user/vault-librarian.timer` (every 30min)
- Script: `.hermes/scripts/vault_librarian.py`
- Reports to: `Operations/Vault Librarian Report.md`

### Layer 2 — inbox-scanner (Hermes cron)

**LLM reasoning** — classification, Kanban card creation, ClickUp reminders, Slack Block Kit summaries via `vault-triage` skill.

- Cron: `inbox-scanner` (id `4836310a8de8`), `no_agent=true`, every 30min
- Script: `.hermes/scripts/inbox_scanner_runner.py`
- Skills: `vault-triage,obsidian,vault-lookup-by-uid`
- Toolsets: `hermes-cli,opencode,mcp-pantheon`

### Inbox State Model

Each Inbox note carries a `triage:` frontmatter key:

| Value | Meaning | Re-triaged? |
|---|---|---|
| *(absent)* | never seen | yes |
| `done` | handled | only if body changes |
| `parked` | awaiting Zack | never |
| `discarded` | stub | never |

Legacy `status:` values (`processed`, `draft`, `archived`) are still read for backward compatibility.

### Quick Diagnostic

```bash
# Inbox state at a glance
cd /mnt/z/pantheon/vault/ZNH/Inbox
for f in *.md; do
  state=$(grep -m1 "^triage:" "$f" | sed 's/.*: *//' | sed 's/"//g')
  echo "$(printf '%-12s' ${state:-none}) | $f"
done
```

### Full Architecture Reference

See `references/vault-processing-two-layer-architecture.md` for the complete design, failure modes, and verification commands.
