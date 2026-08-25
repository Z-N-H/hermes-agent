# Two-Layer Vault Processing Architecture

## The Pattern

The vault inbox (and other recurring vault-wide work) is split across **two scheduling layers** with complementary strengths:

```
Layer 1 — Systemd Timer (vault-librarian)
├── Mechanical, deterministic, zero token cost
├── Runs every 30 minutes
├── Handles: move tracking, filing done/discarded notes,
│            discard guard, uid repairs, nudge on parked notes
└── Re-triages un-triaged notes via direct hermes chat -q calls
    (max 5 per run, 2 concurrent)

Layer 2 — Hermes Cron (no_agent=true runner)
├── Full LLM reasoning when triggered
├── Runs every 30 minutes
├── Handles: classification, Kanban card creation, Slack summaries,
│            ClickUp reminders, filing to correct folders
└── Only spends tokens when there's actual work
```

## Why Two Layers

| Concern | Layer 1 (systemd) | Layer 2 (cron) |
|---|---|---|
| Token cost | Zero (stdlib Python) | Proportional to backlog |
| Reliability | Deterministic — same inputs = same outputs | LLM can stall, hallucinate, or stay silent |
| Speed | Seconds per run | Minutes per triage (hermes chat -q) |
| What it can do | File notes, move-track, read frontmatter | Classify, create cards, send Slack, dispatch work |
| Failover | Each layer runs independently; if one fails, the other still fires |

## Implementation Detail

### Layer 1 — vault-librarian systemd timer

- **Timer unit:** `~/.config/systemd/user/vault-librarian.timer` — `OnUnitActiveSec=30min`
- **Service unit:** `~/.config/systemd/user/vault-librarian.service` — runs `vault_librarian.py`
- **Script:** `.hermes/scripts/vault_librarian.py` — stdlib Python, performs all mechanical operations
- **Reports to:** `Vault Librarian Report.md` in the vault's `Operations/` folder
- **Re-triage budget:** `MAX_RETRIAGE_PER_RUN = 5` (notes needing LLM), `MAX_CONCURRENT = 2` (parallel hermes sessions)
- **Age thresholds:** 2h settle before triaging, 48h before nudging on parked notes

### Layer 2 — inbox-scanner Hermes cron

- **Cron job:** `inbox-scanner` (id `4836310a8de8`), schedule `every 30m`, `no_agent=true`
- **Runner script:** `.hermes/scripts/inbox_scanner_runner.py` (also archived as a linked script under the `pantheon-operations` skill at `scripts/inbox_scanner_runner.py`)
- **How it scans:** Reads `triage:` frontmatter directly from each `.md` file in `Inbox/` — no side-car state file needed. No `.scanner-state.json` dependency. Eight output buckets: untriaged, failed, parked, done, discarded, unreadable, plus legacy status: compatibility.
- **Conditional LLM:** Only fires `hermes chat -q` when there are actionable notes (untriaged + failed + done + discarded > 0). Empty inbox = zero tokens, zero Slack, zero output.
- **Skills loaded:** `vault-triage` (classification + actions), `obsidian` (vault operations), `vault-lookup-by-uid` (cross-ref uid links)
- **Toolsets:** `hermes-cli,opencode,mcp-pantheon` (for card creation, ClickUp reminders)
- **Output delivery:** On success, the runner produces empty stdout and exits 0 — `no_agent=true` interprets empty stdout as silent, so nothing is delivered through cron. Slack delivery happens via `send_message` inside the `hermes chat -q` session. On failure (hermes exits non-zero), the runner prints error details to stdout so cron delivers the failure report.
- **Fire-and-forget dispatch:** The runner uses `subprocess.Popen()` (not `subprocess.run()`), kicking off hermes in the background with stdin/stdout/stderr to DEVNULL. It returns immediately (exit 0) without waiting for hermes to finish. This is **required** because the cron scheduler kills scripts that run longer than 120s, and hermes can take several minutes per batch. The hermes process handles all work (note processing, card creation, Slack delivery) independently in the background.
- **Slack summary:** The agent sends a single Block Kit message at the end of each run with what was classified, filed, carded, parked, and what failed.

## Why Not Just One Layer

- **Hermes cron alone** burns tokens on every tick, even when nothing changed. The old inbox-scanner cron had 1,046 runs, almost all producing "silent (empty output)". An empty-check LLM call costs ~10K+ tokens every tick with no benefit.

- **Systemd timer alone** can't do anything an LLM is needed for — classification, card creation, contextual Slack messages — so the inbox never fully drains (notes get triaged but not filed, cards aren't created, you never hear about what needs your input).

## Failure Mode: One Note Holds Up the Queue

When a single note keeps failing triage (e.g., `hermes chat -q` exits 0 but writes no `triage:` frontmatter), it consumes the budget every run:

- Layer 1's `audit_inbox()` has `MAX_RETRIAGE_PER_RUN = 5`. If note X fails on every run, only 4 other notes get processed per cycle.
- Layer 2 catches the overflow: notes that didn't fit in layer 1's budget or were missed for any reason get processed in the next cron cycle.
- After 3 consecutive failures on the same note, layer 1 sends a Slack DM escalation: `"triage has failed 3 times running; needs a look"`.

The fix for a persistently failing note is usually one of:
- Missing/uninstalled skill named in the `vault_triage.py` `SKILLS` constant (Hermes exits 1 with "Unknown skill(s)")
- Wrong model configured for cron runs (deprecated or overloaded)
- A note with unusual content that confuses the classification skill

## Scheduling

Both layers run every 30 minutes, naturally de-skewed after the first cycle because the systemd timer counts from `OnUnitActiveSec` while the cron ticker runs on the schedule clock.

```ini
# Layer 1: vault-librarian.timer
OnBootSec=15min
OnUnitActiveSec=30min

# Layer 2: Hermes cron job
schedule: "every 30m"
no_agent: true
script: inbox_scanner_runner.py
workdir: /mnt/z/pantheon
```

## Verification

```bash
# Layer 1 status
systemctl --user status vault-librarian.timer
journalctl --user -u vault-librarian.service --no-pager -n 20

# Layer 2 status
hermes cron list | grep -A10 "inbox-scanner"
pgrep -f "hermes.*gateway"   # gateway must be running for cron to fire

# Inbox status — which notes are stuck and why
cd /mnt/z/pantheon/vault/ZNH/Inbox
for f in *.md; do
  state=$(grep -m1 "^triage:" "$f" | sed 's/.*: *//' | sed 's/"//g')
  echo "$(printf '%-12s' ${state:-none}) | $f"
done

# Most recent librarian report
cat /mnt/z/pantheon/vault/ZNH/Operations/Vault\ Librarian\ Report.md
```

## Cron Job Creation (for reference)

The inbox-scanner cron was created with:

```bash
hermes cron create \
  --name "inbox-scanner" \
  --schedule "every 30m" \
  --no_agent true \
  --script inbox_scanner_runner.py \
  --deliver local \
  --workdir /mnt/z/pantheon
```

Note: `--deliver local` is used because delivery happens via `send_message` inside the agent session, not through cron's output delivery. With `no_agent=true`, empty stdout means silent delivery regardless of the deliver target.
