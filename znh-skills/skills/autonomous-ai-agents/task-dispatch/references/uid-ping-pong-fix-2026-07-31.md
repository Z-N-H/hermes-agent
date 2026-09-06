# UID Ping-Pong Fix (2026-07-31)

> **Note (2026-08-03):** This incident and fix are specific to the Project
> Manager plugin era. The board has since migrated to TaskNotes (see
> `docs/plans/2026-07-31-tasknotes-migration.md` in the vault), which does
> surgical per-file writes via Obsidian's Bases engine instead of
> Project Manager's rename-on-save + whole-project-cache behaviour — the class
> of bug described below has not recurred. `is_plugin_owned()` is kept as
> cheap insurance pending more real-world TaskNotes usage rather than removed
> outright. Paths below reflect the vault layout at the time of the incident
> (`Engine/🚀 Operations_tasks/`, `Engine/.board-events.jsonl`); cards and the
> event log now live under `TaskNotes/Tasks/` and `TaskNotes/.board-events.jsonl`
> respectively — this doc is kept as historical root-cause record, not a
> current runbook.

## Problem

Cards dragged to the **Ready for Agent** column in the Obsidian Project Manager Kanban board vanished from the rendered view. On disk, their `status` field showed the original value (e.g. `todo`, `blocked`) — the status change was never persisted.

## Root Cause

A two-sided conflict between `trigger_scanner._stamp_uid()` and the Project Manager plugin:

1. **`_stamp_uid()`** in `trigger_scanner.py` wrote a `uid` field to every card file it scanned, ensuring Hermes-internal uid consistency.
2. The **Project Manager plugin** also manages the `uid` field — and renames card files on save from slug-based names (e.g. `vault-librarian--report-table,-manual-trigger-shortcut,-edit.md`) to title-based names (e.g. `Vault librarian.md`) — see `obsidian-filename-heading-sync` and the plugin's `rename-on-save` behaviour.
3. Every time `_stamp_uid` touched a card file, it invalidated the plugin's internal reference to that card (because the uid was now different from what the plugin expected). On the next save, the plugin recreated the file — new name, new uid, but the **original status**, not `ready-for-agent`. The old file was deleted, the new one orphaned from the board's `taskIds` array.
4. Additionally, the plugin's rename-on-save created duplicate card files with the same task ID (slug-named + title-named), causing `TaskFileNameConflict` errors on subsequent saves — which silently prevented any status write at all.

## Fix (commit `c0b07cc`)

Three changes in `vault/ZNH/scripts/`:

1. **`vault_board.is_plugin_owned(path)`** — marks the board note (`🚀 Operations.md`) and its `_tasks/` directory as plugin-managed files. Outside writers must not touch the uid of these files.
2. **`trigger_scanner._stamp_uid`** — checks `is_plugin_owned()` before stamping. Plugin-owned files are skipped entirely. This kills the ping-pong.
3. **Deduped the bridge card** — the duplicated card (slug-named + title-named with same task ID) was resolved by keeping the plugin-conventional title-named file, removing the stale checklist ghost, and resyncing the board.

## Verification

- 70/70 tests pass, including a new regression test for `is_plugin_owned`
- Dry-run scan correctly detects a `ready-for-agent` + Hermes-assigned card and builds the dispatch prompt
- Service restart confirmed; touching the board and a card produces **no uid churn** (previously every touch generated one)
- Board audit clean (0 missing/unparseable cards)

## Verification Commands

```bash
# Check the fix is applied
cd /mnt/z/pantheon/vault && git log --oneline -1
# Should show c0b07cc

# Check board health
python3 vault/ZNH/scripts/vault_board.py audit

# Simulate a scan (dry-run)
python3 vault/ZNH/scripts/trigger_scanner.py --dry-run

# Check event log for dispatch activity
tail -20 vault/ZNH/Engine/.board-events.jsonl
```

## Related Files

- `vault/ZNH/scripts/vault_board.py` — `is_plugin_owned()` helper
- `vault/ZNH/scripts/trigger_scanner.py` — `_stamp_uid()` skip logic
- `vault/ZNH/Engine/.board-events.jsonl` — audit trail
