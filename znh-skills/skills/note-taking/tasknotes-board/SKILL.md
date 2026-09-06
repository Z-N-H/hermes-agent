---
name: tasknotes-board
description: "Use when creating or reading Obsidian TaskNotes task cards."
platforms: [linux]
metadata:
  hermes:
    tags: [obsidian, tasknotes, kanban, board, vault, task-cards]
    related_skills: [vault-lookup-by-uid, task-dispatch, using-se-ranking-mcp]
---

# TaskNotes Board — the Obsidian task system

The user's task board is the **TaskNotes plugin** (callumalpass/tasknotes),
NOT the retired Project Manager / `Engine/🚀 Operations` board. ZACK
CORRECTED THIS TWICE (Aug 2026): "we don't use the engine folder anymore"
and "we moved away from project manager to tasknotes". Any task-related
read or write goes to `TaskNotes/` — never `Engine/`.

## Board layout

- **Cards**: `vault/ZNH/TaskNotes/Tasks/<slug>.md` — plain markdown notes
  with YAML frontmatter (TaskNotes reads `status`/`priority`/etc. live via
  Obsidian's metadataCache; a card is just its file).
- **Archive**: `TaskNotes/Archive/<year>-<month>/` for done cards.
- **Rendered views**: `TaskNotes/Views/*.base` (kanban-default.base is the
  board; also tasks/agenda/calendar bases).
- **User guide**: `TaskNotes/Start Here.md`.
- **Single writer**: `vault/ZNH/scripts/vault_board.py`. Never hand-edit
  card frontmatter with write_file/patch — it skips the writer lock and the
  audit trail (`TaskNotes/.board-events.jsonl`).
- Status columns: `open` (drafting) → `ready-for-agent` (DISPATCH TRIGGER —
  only this lane hands a card to the agent dispatcher) → `in-progress` →
  `ready-for-review` (agent's own claim of completion, evidence-gated) →
  `done` (Zack-only promotion). There is NO `todo`, `blocked`, or
  `cancelled` status; stuck cards keep their status and carry a
  `blocker_reason` instead.

## Creating a card manually (raw upsert)

Prefer the structured handoff below for OpenCode delegation; use raw
`upsert` only when the template genuinely doesn't fit.

Verified CLI (Aug 2026, `vault_board.py upsert --help`):

```bash
cd /mnt/z/pantheon/vault/ZNH/scripts && python3 vault_board.py upsert \
  --title "Card title" \
  --status ready-for-agent \
  --priority medium \
  --client Thankbox \
  --assignees "OpenCode" \
  --tags "client/thankbox,seo,keyword-research" \
  --source hermes-triage \
  --source-id "<note-uid>-<slug>" \
  --note "[[Source note]]" \
  --body "<full self-contained brief>"
```

CLI facts that differ from older docs:
- `--status` accepts `open|ready-for-agent|in-progress|done` — `todo` no
  longer exists (old examples using `--status todo` will hard-fail).
- `--assignees` is **comma-separated** (`OpenCode,Hermes`), not a JSON array.
- `--body` is accepted and is where the work brief goes. For a handoff card,
  embed the full self-contained plan (research steps, data sources,
  deliverable) so the receiving agent doesn't have to reconstruct it.
- Idempotency is keyed on `(source, source_id)`; triage cards follow
  `source: hermes-triage`, `source_id: <noteuid>-<slug>`.

## Structured handoff to OpenCode (preferred)

When delegating a task to OpenCode, don't free-form the `--body` brief.
Use the template at `references/opencode-handoff-template.md` (six
required sections: Goal, Context & Files, Constraints, Acceptance
Criteria, Verification Steps, Out of Scope) and create the card with the
validating wrapper:

```bash
# 1. Copy the template somewhere writable and fill every section
cp /mnt/z/pantheon/.hermes/skills/note-taking/tasknotes-board/references/opencode-handoff-template.md /tmp/handoff.md

# 2. Validate + create (validation is code-enforced; a missing or empty
#    section refuses the handoff with exit 1)
cd /mnt/z/pantheon/vault/ZNH/scripts && python3 vault_handoff.py create \
  --title "Short task title" \
  --brief /tmp/handoff.md \
  --tags "client/thankbox,seo" \
  --note "[[Source note]]"
```

Facts:
- Defaults are the handoff path: `--status ready-for-agent`,
  `--assignees OpenCode`, `--source hermes-handoff`. Override only when
  deliberately drafting (`--status open`).
- `source_id` defaults to the slugified title, so re-running `create`
  with the same title updates the same card instead of duplicating it.
- Use `vault_handoff.py check --brief FILE` to validate without creating,
  and `--dry-run` to preview the card.
- Acceptance criteria need at least one `- [ ]` checkbox, each
  independently verifiable — OpenCode's run is judged against them.

## Client/project assignment — user requirement (Aug 2026)

Every task card must be **assigned to a client/project**, and that
client must be **visible on the card**, not just buried in frontmatter.

- Pass `--client "<name>"` (and `client/<name>` in `--tags`) on every
  `vault_board.py upsert` / `vault_handoff.py create`.
- **Visibility trap:** `--client` writes the `client:` frontmatter field, but
  the rendered Kanban board does NOT show it unless the Bases view selects that
  property in its card layout. Example failure: uid `G6W3SA6F`
  (`build-recipient-christmas-card-categorylanding-pages...md`) had
  `client: Thankbox` in frontmatter yet the titled/rendered card showed no
  client context at all. So just setting the field is not enough to satisfy a
  "client visible on the card" ask — the `.base` render must surface it too
  (Zack explicitly chose surfacing the field over `[Client]` title prefixes).
- The canonical list of clients is `vault/ZNH/Clients/` (one dir/file per
  client: `Acme Corp`, `Thankbox`, `Neary-Hayes`, `Nous Research`, etc.).
- **The `client` value is NOT free-text — it MUST always be one of the entries
  present in `vault/ZNH/Clients/`** (exact name; entries are both `.md` file
  stems like `Acme Corp` and directories like `Thankbox`/`Neary-Hayes`). Not an
  invented name, not a generic internal label. URGE: do NOT classify
  internal/board-tooling meta-tasks as client **Pantheon** — the user corrected
  this (Aug 2026): a vault/board meta-task about the vault's own tooling gets the
  user's own client, **Neary-Hayes** (tag `client/neary-hayes`). He owns it; it
  is a real entry in Clients/.
- Reference card tracking the enforcement work (client mandatory + surfaced):
  `TaskNotes/Tasks/enforce-mandatory-clientproject-on-task-cards-and-surface.md`
  (uid `fZr6xxuc`).
- **Status of the enforcement (verified 2026-08-16, card `fZr6xxuc` closed to
  ready-for-review):** `vault_board.py`/`vault_handoff.py` now REFUSE any
  `--client` that isn't a real `Clients/` entry (exit 2, lists valid clients),
  require a client when creating a NEW card into a workable status (`open`
  drafts may omit it), and the `kanban/agenda/calendar/tasks-default.base`
  views now render `client` on each card. So passing a bogus client now fails
  loudly — no longer silently accepted. If you hit a new card-creation error,
  check the `ClientError`/`validate_client` path in `scripts/vault_board.py`
  before assuming a tooling regression.

## Workflow lessons (Aug 2026 session)

1. **Plan the task, don't audit the infrastructure.** When the user says
   "plan X and create a card for handoff", deliver the plan (what to
   research/build, data sources, deliverable shape) and create the card.
   Do NOT go probe MCP hub health, dispatcher state, config files, or
   plugin data.json unprompted — "the system already knows everything
   else". One probing command during the session was denied as noise.
2. **Check for an existing card before creating** (idempotency: matching
   source_id/slug). The prior recipient-keyword Christmas task existed as a
   sibling card; the bulk-persona task was genuinely new.
3. **Link the card to its source note** via `--note [[wikilink]]` and keep
   `client` + `client/...` tags so Bases filters work.
4. **Seasonality flag for Christmas/keyword-volume cards**: annual average
   volume understates Nov–Dec peaks — the agent should flag it, not kill
   the keyword.

## Create-card pitfalls

- **`--title` determines the auto-generated filename, and punctuation is stripped WITHOUT a separator.** A title like `Build recipient Christmas card category/landing pages` produces filename `build-recipient-christmas-card-categorylanding-pages...md` — the `/` collapses into `categorylanding`, gluing words together (verified 2026-08-16 with `vault_board.py upsert`). `--source-id` does NOT control the filename; only `--title` does. If a clean slug matters, leave `/`, `&`, `(`, `)` etc. out of the `--title`. But the board renders from frontmatter `title:`, so an ugly filename is cosmetic — don't burn tool calls hunting for a clean slug.
- **`upsert` prints the card path relative to the scripts dir** (`TaskNotes/Tasks/<card>.md`). To read the file back, use the absolute path `vault/ZNH/TaskNotes/Tasks/<file>.md`; `search_files` resolves relative to session cwd and returns "Path not found" for the relative string if cwd differs.

## Research-task handoff specifics

For keyword-volume research cards (e.g. "dig for volume on X"), the brief
should name: exact-match volume via `seranking_DATA_exportKeywords`
(sources `uk` + `us` — NOT `getSearchVolume`, which inflates), related +
similar keyword expansion, difficulty/CPC as intent signals, and the
deliverable verdict. See the `using-se-ranking-mcp` skill for the query
tier. Note: se-ranking mounts under the pantheon MCP hub and can be down —
if the card's core data source is failing, flag it to Zack rather than
letting the agent silently stall.

## Related skills / stale docs

- `kanban`, `task-dispatch`, and `obsidian` (its "Finding What to Work On"
  section and `references/tasknotes-plugin-schema.md`) have been updated
  (2026-08-03) to describe the current TaskNotes layout and statuses instead
  of the retired Engine/Project Manager board — they should now agree with
  this skill. If they drift again, trust this skill and re-port.
- Once confirmed stable, this skill is a candidate for `hermes curator
  adopt` / removal as a standalone skill, since its content now duplicates
  the updated `kanban`/`task-dispatch`/`obsidian` skills.
