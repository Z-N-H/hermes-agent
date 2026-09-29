# Vault Librarian — Systemd Timer Reference

Full deployment record from 2026-07-29/30. The vault-librarian script monitors the Obsidian vault for moved notes and stale Inbox items.

## Architecture Decision

| Aspect | Chosen | Rejected |
|--------|--------|----------|
| Scheduler | systemd timer (every 3h) | Hermes cron job (`hermes cron create`) |
| Execution | standalone Python script | LLM-driven cron agent |
| Side effects | `--no-retriage` flag suppresses agent actions | Full auto-triage loop |

**Rationale:** A vault maintenance script that scans files and writes JSON logs needs zero LLM involvement. Hermes cron would burn tokens on every tick. The systemd timer runs the script directly — no gateway dependency, no token cost, more reliable timing. The `--no-retriage` flag means the script safely does filing and uid repairs automatically but never creates Kanban cards, ClickUp tasks, or Slack messages — those are gated behind an explicit dispatch by the user.

## Script Location

```
/mnt/z/pantheon/.hermes/scripts/vault_librarian.py
```

Stdlib-only Python. Supports `--dry-run` for safe testing. Uses `vault_uid.py` helpers for uid resolution. Atomic log writes (temp file + os.replace).

## Systemd Units

### vault-librarian.service

```ini
[Unit]
Description=Vault librarian — check for moved notes and stale inbox items

[Service]
Type=oneshot
ExecStart=/mnt/z/pantheon/.hermes/scripts/vault_librarian.py --no-retriage
WorkingDirectory=/mnt/z/pantheon
User=%u
```

### vault-librarian.timer

```ini
[Unit]
Description=Run the vault librarian every 3 hours

[Timer]
OnCalendar=*:0/180
Persistent=true

[Install]
WantedBy=timers.target
```

## Deployment

```bash
systemctl --user enable --now vault-librarian.timer
```

## Verification

```bash
systemctl --user status vault-librarian.timer     # "active (waiting)", shows next trigger
systemctl --user status vault-librarian.service    # "inactive (dead)" — oneshot, exits after run
journalctl --user -u vault-librarian.service       # stdout/stderr from last run
```

## Hermes Cron Cleanup

When migrating from Hermes cron to systemd timer, remove the old job:

```bash
hermes cron remove <job-id>
```

The old Hermes cron registration and the systemd timer will compete if both are active. Always remove the cron job before or immediately after enabling the timer.

## What the Script Does

1. Scans `.md` files in `vault/ZNH` modified 2–12 hours ago (skips `.obsidian`, `Templates`)
2. Resolves each note's `uid:` frontmatter via `vault_uid.py`
3. Compares current paths against `vault_librarian_log.json`
4. Detects moves: logs `{uid, old_path, new_path, timestamp}` to the log (capped at 500 entries)
5. Flags inbox notes older than 24h as mislocated (with `[client note?]` tag if filename/frontmatter suggests client content)
6. Brief stdout summary for monitoring

## First-Run Output Pattern

```
Moves:
  none detected

Mislocated (Inbox > 24h):
  Inbox/Something.md (89h old)
  ...

note: N recently-modified note(s) have no uid; moves untrackable

summary: 0 move(s), N mislocated, K without uid, M notes tracked
```
