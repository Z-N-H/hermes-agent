# Session Example: Debugging the Inbox Scanner Cron Job

## Session: 2026-07-24

## Scenario
An Obsidian inbox scanner cron job was configured with:
- Correct script at `.hermes/scripts/inbox_scanner.py`
- Schedule: `every 30m`
- Skills: `obsidian, slack-formatting`
- Delivery: `all`

Despite correct configuration, the job **never ran** — `last_run_at` stayed `null` for 30+ minutes.

## Root Cause #1: Gateway Not Running

```bash
$ hermes cron status
✗ Gateway is not running — cron jobs will NOT fire
```

The cron scheduler is part of the Hermes gateway process. Without the gateway, jobs are registered in the config DB but never dispatched. `hermes cron list` shows the config; `hermes cron status` shows whether the scheduler is alive.

**Fix:** Start the gateway (`hermes gateway` foreground, or `hermes gateway install` as a service). For one-shot testing, use `hermes cron tick`.

## Root Cause #2: Script Path Resolution Bug

The script used dynamic path resolution:
```python
VAULT = Path(__file__).resolve().parent.parent  # intended: /mnt/z/pantheon/vault/ZNH
```

When the script ran from `.hermes/scripts/`, this resolved to:
```python
# __file__ = /mnt/z/pantheon/.hermes/scripts/inbox_scanner.py
# .parent.parent = /mnt/z/pantheon/.hermes/
# INBOX = /mnt/z/pantheon/.hermes/Inbox/  ← DOES NOT EXIST
```

The script reported `total_inbox_files: 0` and output `NO_ACTION_REQUIRED` every run, so the LLM phase had nothing to process. This is not a cron system bug — it's a script design bug that only manifests when the script is invoked from an unexpected location.

**Fix:** Hardcode the absolute path:
```python
VAULT = Path("/mnt/z/pantheon/vault/ZNH")
```

## What We Learned

1. **First diagnostic for any non-firing cron job:** `hermes cron status` — check gateway is running.
2. **Test new scripts manually** before wiring them into cron: `python3 .hermes/scripts/<script>.py` — catch path resolution bugs immediately.
3. **Use `hermes cron tick` for one-shot testing** — it runs due jobs without starting the full gateway daemon.
4. **Scripts in `.hermes/scripts/` should use absolute paths** for data directories, not dynamic `Path(__file__)` resolution, because the script's location doesn't reflect the data's location.
