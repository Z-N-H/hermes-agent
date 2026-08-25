# Kanban Completion Tracking

> **DEPRECATED: Marker-based protocol (2026-07-28 → 2026-07-29).**  
> Replaced by direct card frontmatter updates. See below.

## Current Approach (2026-07-29+)

Card state is tracked solely via YAML frontmatter in the card file under `TaskNotes/Tasks/` (migrated from Project Manager's `Engine/🚀 Operations_tasks/` to TaskNotes in the 2026-08-02 board migration — see `docs/plans/2026-07-31-tasknotes-migration.md`). The `trigger_scanner.py` file watcher monitors vault `.md` files and reacts to frontmatter changes.

### Lifecycle

| Event | Action | Who |
|-------|--------|-----|
| Work dispatched | Set `status: in-progress` in card frontmatter | Hermes |
| Work completes | Set `status: ready-for-review`, `progress: 100` in card frontmatter — Zack promotes to `done` by hand | Hermes |
| File watcher detects change | Sends Slack DM via `vault_kanban_dispatch.py` | trigger_scanner.py |

### No markers

The `.hermes/task-completions/` directory and `vault_completion_watcher.py` have been removed. The card file's own frontmatter change IS the completion signal — the file watcher sees it, dispatches any follow-up logic, and notifies the user via Slack.

### Why the change

The marker system introduced a second state store outside the vault. Markers didn't trigger the vault file watcher, so they sat unprocessed until a Kanban card happened to change, causing sync failures and stalled completions.
