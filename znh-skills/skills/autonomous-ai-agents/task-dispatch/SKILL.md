---
name: task-dispatch
description: Dispatch tracked work to OpenCode, tracking state on the Obsidian Kanban card via vault_board.py — the single writer and the single source of truth. No marker files, no hand-edited frontmatter.
version: 3.2.0
platforms: [linux]
environments: [hermes]
metadata:
  hermes:
    tags: [task, dispatch, kanban, tracking, completion]
    related_skills: [opencode-worker]
---

# Task Dispatch — Kanban Card Protocol (v3)

## Overview

The Kanban card's YAML frontmatter is the single source of truth for task
state — **but you never edit that frontmatter yourself.** All card writes go
through `vault_board.py`. There is no board note and no `taskIds` array
anymore (that bookkeeping was Project-Manager-only, removed when the board
migrated to TaskNotes — see `docs/plans/2026-07-31-tasknotes-migration.md` in
the vault); the Kanban view is a live Obsidian Bases query
(`TaskNotes/Views/kanban-default.base`) over the card files themselves, so a
card's own frontmatter *is* the board state. `vault_board.py` still matters
as the single writer — it handles the uid, the writer lock, and an
event-log entry for every transition.

## Protocol

### 1. On dispatch

The card is usually already claimed (`status: in-progress`) by
`vault_kanban_dispatch.py` before you ever see it — the dispatcher triggers
only when a card is moved to the **Ready for Agent** column (`open` is a
drafting lane and never dispatches). If you dispatch work for a card that
hasn't been through that lane:

```bash
cd /mnt/z/pantheon/vault/ZNH/scripts && python3 vault_board.py upsert \
  --title "<card title>" --status in-progress --source opencode \
  --source-id "<unique-id>"
```

Or, if you already know the card path, `update_card_by_path` is what the
dispatcher itself uses — from the CLI there is no direct path-update
subcommand, so prefer `upsert` with the card's `--source`/`--source-id`.

### 2. On completion (after notify_on_complete fires)

```bash
cd /mnt/z/pantheon/vault/ZNH/scripts && python3 vault_board.py complete \
  --source opencode --source-id "<unique-id>" \
  --result "What was actually done, in one or two sentences."
```

This sets `status: ready-for-review`, `progress: 100`, appends a dated `## Result`
section to the card body, and logs the transition. There's no separate board
index to resync — the Kanban view reads this card's frontmatter live.

**Agent completion never lands on `done` directly — it lands on `ready-for-review`.**
Your claim of completion is not the final verdict; Zack reviews the work and
promotes `ready-for-review` -> `done` himself by dragging the card in Obsidian. You
have no tool for that transition and should not ask for one.

**`ready-for-review` is evidence-gated.** `vault_board.py` refuses to move a card to
`ready-for-review` unless there is independent proof the work happened: an attached
PR, a Pantheon manifest at `done`, or a recent exit-0 completion record in
`~/.hermes/process-completions.jsonl` that matches the card. A refused
transition exits non-zero with the reason, and the refusal itself is logged
in `TaskNotes/.board-events.jsonl`. If you can't point at completed work,
leave the card at `in-progress` and set a `blocker_reason` instead. Never
pass `--force` to route around the gate; it exists for Zack, and its use is
logged as a manual override.

### 3. If you get stuck

There is no `blocked` status. Leave the card's `status` as-is (usually
`in-progress`) and set a reason via `update --blocker-reason "..."`, so it
shows up in the board's "Needs me" view and the daily note instead of
silently stalling:

```bash
cd /mnt/z/pantheon/vault/ZNH/scripts && python3 vault_board.py update \
  --path "TaskNotes/Tasks/<card>.md" --blocker-reason "..."
```

### 4. For ad-hoc tasks without a card

If the work doesn't have a Kanban card yet, create one via `vault_board.py`:

```bash
cd /mnt/z/pantheon/vault/ZNH/scripts && python3 vault_board.py upsert \
  --title "Brief task title" \
  --status open \
  --source opencode \
  --source-id "<unique-id>" \
  --assignees "Hermes"
```

That is the whole job — `vault_board.py` creates the card file under
`TaskNotes/Tasks/`, which the live Kanban view picks up immediately. There is
no board note and no separate index to update, so there is nothing to
hand-edit afterwards.

## Troubleshooting: Ready for Agent not dispatching

If cards moved to the **Ready for Agent** column are not being picked up
(they "disappear" from the rendered board, remain at their original status,
or nothing dispatches):

1. **Check the card on disk first.** Never trust the rendered kanban view —
   read the raw file and check git status simultaneously:
   ```bash
   cd /mnt/z/pantheon/vault/ZNH/TaskNotes/Tasks
   grep "^status:\|^uid:" <card-name>.md
   git status --short <card-name>.md
   ```
   This immediately tells you whether the status actually changed and whether
   the file was renamed (deleted old + untracked new = uid ping-pong, see
   below).

2. **UID ping-pong — historical, Project Manager era only.** Before the
   board migrated to TaskNotes, `trigger_scanner._stamp_uid()` writing a
   `uid` field to a card could collide with the Project Manager plugin's own
   uid management and rename-on-save behaviour, orphaning the card from the
   board's `taskIds` array. TaskNotes doesn't rename files on save and does
   surgical per-file writes rather than a whole-project rewrite, so this
   failure mode hasn't recurred (verified empirically during the migration —
   see `docs/plans/2026-07-31-tasknotes-migration.md` Task 0). Full root
   cause and fix: `references/uid-ping-pong-fix-2026-07-31.md`.
   `vault_board.is_plugin_owned(path)` (which the fix introduced) is kept as
   cheap insurance regardless.

3. **Check TaskNotes' status configuration.** TaskNotes' settings live in
   `.obsidian/plugins/tasknotes/data.json` (device-local, not synced).
   Verify `ready-for-agent` is present among its configured Status Values —
   if it's missing, TaskNotes won't recognise cards in that status and the
   Kanban view (`TaskNotes/Views/kanban-default.base`) may not render them
   in a distinct column. Fix via Settings → TaskNotes → Task Properties →
   Status Values in Obsidian (not something to script — it's local
   per-device config, not synced by default).

4. **Verify `trigger_scanner.py` is actually running.**
   `vault_kanban_dispatch.py` is triggered by `trigger_scanner.py` — if the
   scanner isn't alive, no card will ever be picked up regardless of status:
   ```bash
   ps aux | grep trigger_scanner
   ```
   Also check if the gateway (which may embed the scanner) is running the
   **expected version** — after a `hermes update`, the gateway may still be
   running old code if not restarted:
   ```bash
   systemctl --user status pantheon-hermes-gateway.service
   hermes --version   # compare against runtime version
   ```
   If the scanner is not running, restart the gateway:
   ```bash
   systemctl --user restart pantheon-hermes-gateway.service
   ```

5. **TaskNotes fails to persist a status change to disk.** Not yet observed
   under TaskNotes (unlike the old Project Manager plugin, it doesn't rename
   files on save or hold a whole-project in-memory cache — see Task 0 of the
   migration plan for the empirical verification), but if a drag-and-drop
   move doesn't stick: check the card file's `updatedAt` frontmatter and
   `stat` timestamp for a recent change. No change means the move only
   happened in Obsidian's UI state and never reached disk.
   ```bash
   grep "^status:\|^uid:" /mnt/z/pantheon/vault/ZNH/TaskNotes/Tasks/<card>.md
   ```

6. **Check the board events log.** `vault_kanban_dispatch.py` logs every
   scan cycle, claim, and refusal to `TaskNotes/.board-events.jsonl`. It also
   logs a scan summary even when no actionable cards are found:
   ```bash
   tail -20 /mnt/z/pantheon/vault/ZNH/TaskNotes/.board-events.jsonl
   ```
   Look for entries like `card_claimed` (success), `card_scan_no_work` (no
   ready-for-agent cards found), or `card_blocked` (dispatcher tried but
   something went wrong). An empty or missing log means the dispatcher never
   ran.

7. **Gateway restart after update.** After an update (especially a major
   version jump), the gateway service must be restarted to pick up the new
   code. (The supported update path — `safe_hermes_update.sh` — already does
   this restart and log-checks the fresh boot.) The scanner and dispatcher
   may be embedded in the gateway process or run as separate systemd units —
   check both:
   ```bash
   systemctl --user restart pantheon-hermes-gateway.service
   ```

8. **Fallback: manually dispatch.** If the dispatcher isn't available, use
   `vault_board.py` directly:
   ```bash
   cd /mnt/z/pantheon/vault/ZNH/scripts
   python3 vault_board.py upsert --title "<card title>" \
     --status in-progress --source opencode --source-id "<id>"
   ```

## Rules that keep the board truthful

- **Never** use `write_file`/`patch`/`sed` to change a card's `status:` (or
  any other frontmatter). Hand edits skip the writer lock and the event
  log, and the `task_completion_guard` plugin vetoes hand-written
  `status: done` outright.
- Every transition you make is recorded in `TaskNotes/.board-events.jsonl`
  with actor and reason. Report only what you actually did.
- If a `complete` is refused for lack of evidence, the correct response is
  to leave the card `in-progress` with a `blocker_reason` — not retrying,
  not `--force`, not editing the file by hand.

- **UID ping-pong — historical, Project Manager era only.** See item 2 above
  and `references/uid-ping-pong-fix-2026-07-31.md`. Not applicable to
  TaskNotes as currently understood.

- **Obsidian Sync limitation: changes on disk not reflected in UI.** The
  headless sync daemon (`ob-headless-sync.service`) on bazzite detects files
  in `TaskNotes/Tasks/` as \"new\" but may not upload them to
  Obsidian Sync cloud (shown as \"New file... Fully synced\" without
  \"Uploading file\" / \"Upload complete\" in the daemon log). When this
  happens, the card files on disk have the correct status, but Obsidian on
  pop-os-1 pulls its stale cloud copy on restart.
  **Fix:** Touch one of the affected card files to force a re-sync, then
  check the daemon log for actual uploads. If `TaskNotes/Tasks/` files still
  don't upload, restart the sync daemon:
  ```bash
  touch "vault/ZNH/TaskNotes/Tasks/<card>.md"
  sleep 3 && journalctl --user -u ob-headless-sync.service -n 5 --no-pager
  systemctl --user restart ob-headless-sync.service
  ```
  If restarting doesn't help, the `TaskNotes/` directory may be excluded
  from Obsidian Sync selective sync settings on pop-os-1. Check Settings →
  Sync → Manage synced folders.

## When to skip card updates

For trivial requests that don't warrant a Kanban card (e.g., "what's the
weather?", "search for X"), skip the card update entirely. Just answer
directly.

## Related files

- **Board tools**: `/mnt/z/pantheon/vault/ZNH/scripts/vault_board.py`
- **Dispatch**: `/mnt/z/pantheon/vault/ZNH/scripts/vault_kanban_dispatch.py`
- **File watcher**: `/mnt/z/pantheon/vault/ZNH/scripts/trigger_scanner.py`
- **Event log**: `TaskNotes/.board-events.jsonl` (append-only audit trail)
- **Board reference**: `kanban` skill's `references/obsidian-operations-board.md`
- **UID ping-pong fix (historical)**: `references/uid-ping-pong-fix-2026-07-31.md` — root cause analysis and fix for cards vanishing from the Ready for Agent column, specific to the retired Project Manager plugin
