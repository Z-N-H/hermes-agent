# Obsidian Operations Board (TaskNotes)

The user's primary task-tracking board lives in Obsidian at:

```
TaskNotes/Tasks/              # Task notes (this IS the board — no separate board note)
TaskNotes/Archive/            # Completed/archived tasks
TaskNotes/Views/kanban-default.base  # Live Obsidian Bases Kanban view over Tasks/
```

There is no board note. TaskNotes replaced the old Project Manager plugin, whose
whole-project in-memory cache could silently revert external writes; the Kanban
view is a live Bases query over `TaskNotes/Tasks/`, reading each card's frontmatter
straight off Obsidian's own metadataCache, so a card file's frontmatter *is* the
board state — no separate index to go stale.

## Board structure

- **Task notes**: each card is a plain markdown file under `TaskNotes/Tasks/<slug>.md`
  with YAML frontmatter — no markdown checklist, no wikilinks to parse.
- **Identification**: `pm-task: true` (a real YAML boolean) marks a file as a card.
- **Task statuses**: `status` frontmatter key, one of exactly five values:
  `open` (drafting area, never auto-dispatched), `ready-for-agent` (hands the card
  to the dispatcher), `in-progress`, `ready-for-review` (agent claims complete,
  pending Zack's sign-off), `done`. There is no `blocked`/`cancelled` status —
  a stuck card stays in its current status and gets a `blocker_reason`
  frontmatter note instead.
- **Archived tasks**: moved to `TaskNotes/Archive/<year>-<month>/` by
  `vault_board.py archive`.
- **Frontmatter tracked per card**: `uid`, `id`, `title`, `status`, `priority`,
  `start`, `due`, `progress`, `assignees`, `tags`, `createdAt`, `updatedAt`, plus
  `client`, `source`, `source_id`, `clickup_task_id`, `clickup_url`,
  `pantheon_branch`, `pr_url`, `note`, `blocker_reason`, `archived_at`.
- **Views**: `TaskNotes/Views/*.base` files (Kanban, agenda, calendar, tasks list,
  etc.) are all live Bases queries over `TaskNotes/Tasks/` — there is no
  `savedViews` frontmatter blob anymore; each view is its own file.

## How to read it

List or grep `TaskNotes/Tasks/*.md` and parse each file's frontmatter, or use
`vault_board.py list [--status open]` on bazzite. Each card is independent —
there's no parent checklist to cross-reference.

## How to create a new task card

Use `vault_board.py upsert --title "..." --status open [--source ... --source-id ...]`
— it is the single sanctioned writer (handles the uid, writer lock, and audit
log). Don't hand-create a note under `TaskNotes/Tasks/` and expect it to behave
like a card unless it carries `pm-task: true` and valid frontmatter.

## Known pitfalls

- Not every open task has a corresponding Hermes Kanban card. The Obsidian board
  is a superset.
- Archived tasks live in dated subdirectories under `TaskNotes/Archive/` — don't
  treat those as open.
- The old Project Manager plugin folder may still be present on disk pending
  removal, but TaskNotes owns all card reads/writes now — don't reintroduce
  Project-Manager-only fields (`projectId`, `parentId`, `type`, `subtaskIds`,
  `dependencies`) when creating or editing cards.
