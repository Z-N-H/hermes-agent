---
name: granola-meeting-filing
description: File new Granola meetings into Obsidian as client tasks.
platforms: [linux]
environments: [hermes]
required_mcp_servers: [pantheon]
---

# Granola Meeting Filing

Pull Granola meetings into the Obsidian vault at `/mnt/z/pantheon/vault/ZNH/`, matched to a client, with action items turned into Kanban cards. Two trigger modes:

- **Webhook mode** (primary, added 2026-09-28): the `granola-meetings` Hermes webhook route fires this skill once per `note.generated`/`note.edited` event with a single note ID. See "Webhook mode" below.
- **Batch mode** (catch-up sweep): the daily `granola-daily-catch-up` cron job runs a full sync diffing against `seen_granola_ids`. Safety net for missed webhooks (Granola disables endpoints after 4 days of failures; ntfy only keeps ~12h of history). See "Fetching meetings".

**REQUIRED:** Load `vault-tagging` before writing any `tags:` — it defines `client/<slug>` / `src/granola` and the `vault_tags.py check` you run before finishing.

## Webhook mode — file ONE meeting by ID

Triggered by the `granola-meetings` route with a prompt carrying `note_id` (the only trusted input — the relayed payload carries no note content, and Granola's signing secret cannot be verified over the ntfy hop, so the payload is a nudge, never a source). Steps:

1. **MCP precondition** — same as below: `mcp__pantheon__search(query="granola")` must return `granola_*` tools, else fire the ntfy alert to `znh-pantheon` and stop.
2. **Dedup against `seen_granola_ids`.** Read `.hermes/scripts/granola_scanner_state.json`. If the ID is already listed, STOP: no note, no card, and reply with exactly `[SILENT]` (Granola retries and `note.edited` re-fires would otherwise spam Slack).
3. **Fetch the meeting fresh by ID** via the hub (`granola_get_meetings` — search/get_schema/execute per the Iron Law below). The webhook `note_id` and the MCP's canonical meeting ID MAY differ: if a direct fetch returns nothing, fall back to `granola_list_meetings` (recent window) and look for the ID anywhere in the returned meeting objects. If neither finds it, the ID is forged/unknown — **exit cleanly: no note, no card, no state change, and reply with exactly `[SILENT]`.** This is expected behavior for bogus payloads, not a failure.
4. **Re-check dedup on the canonical ID.** Once the meeting is resolved, check ITS canonical ID against `seen_granola_ids` too (an already-filed meeting can arrive under a differently-shaped webhook ID). Match → stop as in step 2.
5. **File it** — client matching, note write, Kanban action items exactly as in the sections below — and append the **canonical** ID to `seen_granola_ids` in the same logical step as writing the note.
6. **Notify** — see "Notification": your final reply is the Slack message. `[SILENT]` on dedup-skips and unknown IDs.

## Batch mode — trigger

The `granola-daily-catch-up` cron job invokes `hermes chat -q` with this skill loaded and passes the current `seen_granola_ids` in the prompt. The agent turn's job: fetch whatever is new, file it, append to state. See `docs/plans/2026-08-19-granola-meeting-scanner-design.md` for the architecture.

## MCP availability precondition — check this FIRST, before anything else

The scheduler already guards the coarse case: this skill declares `required_mcp_servers: [pantheon]`, and the `granola-meeting-scanner` job carries that declaration, so if the Pantheon hub is disconnected the run hard-fails before the first inference call. This section remains as defense-in-depth for the failure the scheduler cannot see from outside the hub: hub connected, but Granola unmounted / OAuth expired inside it.

This job cannot do its job without Granola's tools. Before reading state, before any other exploration: run `mcp__pantheon__search(query="granola")` and look at what comes back.

**If it returns zero `granola_*` tools, that IS the "Granola MCP unreachable" failure case below — treat it exactly the same as an explicit connection error or expired OAuth.** Do not:
- fall back to browsing/describing other tools to "see what's available" instead,
- keep going and file a "no new meetings this run" summary — that is a false success, not a null result; you have no idea whether there are new meetings because you never got to ask,
- spend further turns on it at all.

Stop immediately, fire the ntfy alert per below, and end the run. A cron job that can't reach the tool it exists to call has no work it can honestly do — raise, don't pretend to complete.

## State & idempotency

State file: `.hermes/scripts/granola_scanner_state.json`, shape `{"seen_granola_ids": [...]}`.

- **One-time pull only.** A meeting ID in `seen_granola_ids` is NEVER re-fetched or re-filed (no clobbering hand-edits the user has made to the vault note since).
- **First-ever run (= initial full sync):** if the state file is absent or the list is empty, pull ALL accessible meetings and backfill the whole seen list. Subsequent runs only pull new ones.
- Persist each meeting's ID to the list **in the same logical step** as writing its note, so a mid-run failure leaves no partial/duplicate filings.
- If the Granola MCP is unreachable / OAuth expired / the tool-search precondition above came back empty: **do NOT advance state** (safe retry next tick) and fire an **ntfy alert** to topic `znh-pantheon` — OAuth expiry does not self-heal, and neither does a hub that failed to mount the MCP.

## Fetching meetings (Granola via Pantheon MCP)

Reach Granola through the Pantheon MCP hub. **Iron Law: `mcp__pantheon__search` → `mcp__pantheon__get_schema` → `mcp__pantheon__execute` — never skip, never guess tool names/params.**

- Search the hub for `granola` tools with `mcp__pantheon__search(query="granola")`.
- `mcp__pantheon__get_schema(tools=["granola_list_meetings","granola_get_meetings"])` to confirm exact param names.
- `mcp__pantheon__execute(code=...)` — the runnable body is a **severely restricted Python sandbox** (`pydantic_monty`):
  - **NO imports** (no `json`, `os`, `re`, `sys`) — only `call_tool(name, params)` and builtins (`dict/list/str/int/len/range/sorted/...`).
  - **NO `print`** — produce output by `return <native python object>` (auto-serialized). Never `return json.dumps(...)`.
  - Only `return await call_tool("granola_list_meetings", {...})` style.

List meetings, then fetch full content for each **unseen** ID:
```python
raw = await call_tool(
    "granola_list_meetings",
    {"involvement": {"captured_by_me": True, "listed_as_participant": True}},
)
return raw
```
Filter to IDs not in the passed-in `seen_granola_ids`. For each new one, `get_meetings` by ID and keep `title`, `date`/`start_time`, `attendees`, the AI `summary`/notes, and any action items. **Do NOT pull `get_meeting_transcript`** (large, redundant) — summaries/notes only.

## Client matching

Content-based, no schema changes to client notes. Read the client corpus at `/mnt/z/pantheon/vault/ZNH/Clients/*.md` (filenames + aliases/brand/company/attendee names appearing in note bodies). Match against brands/companies and attendee names **mentioned in the meeting itself** (title, attendee list, Granola summary text).

- Confident match → set `client:` and `related: [[Clients/<Client>]]`, tag `client/<slug>` (see `vault-tagging`).
- Low confidence or conflicting signals → leave `client: ""`, tag `needs-triage`, name it in the summary. **A wrong client silently attached is worse than an honest miss — never guess.**

## Writing the note

Flat `Meetings/` folder (not per-client subfolders), matching the existing `Templates/Meeting Note.md` schema. Read the template and one existing example (e.g. `Meetings/Acme Weekly Sync — 2026-06-17.md`) to match shape exactly. Frontmatter (uid via `/mnt/z/pantheon/vault/ZNH/scripts/vault_uid.py` scheme):

```yaml
uid: <8-char handle, vault_uid.py scheme>
type: meeting
title: <Granola title>
date: <meeting date>
source: granola
granola_id: <meeting UUID>          # dedup key
granola_url: "https://notes.granola.ai/d/<meeting UUID>"   # constructed, not returned by the API — see note below
meeting-type: <inferred, best-effort>
attendees: [<names>]
project: <resolved or "">
client: <resolved or "">
decisions-made: <bool, best-effort>
action-items-count: <n>
llm-priority: <best-effort>
llm-context: "<short synthesized summary>"
tags: [meeting, src/granola, <client/<slug> or needs-triage>]   # convention: vault-tagging skill
related:
  - "[[Clients/<Client>]]"          # omit if unresolved
```

`granola_url`: neither `get_meetings` nor `list_meetings` returns a link — construct it from the meeting UUID as `https://notes.granola.ai/d/<granola_id>` (Granola's known note URL scheme). Also add it as a clickable line right under the H1, e.g. `**Granola:** [Open in Granola](https://notes.granola.ai/d/<granola_id>)`, so it's visible without opening frontmatter.

**H1 title always includes the date**, matching the filename: `# <Granola title> — <date>` (em dash, same as the filename's separator — e.g. `# Thankbox SEO standing call — 2026-08-10`). Several meeting titles recur across weeks (standing calls, syncs), so the bare title alone doesn't disambiguate the note when it's open — the date must be there regardless of whether the title happens to be unique this time.

Body: `## Notes` is Granola's `summary` field **verbatim, in full — copy it as one block, do not retype, reword, re-head, reorder, or drop any part of it, including its own trailing "Next Steps" section.** This is the one part of the note that must read as Granola's own words, not this skill's. Do not normalize its formatting (leave escaped characters, curly quotes, etc. exactly as returned) — treat the fetched string as opaque, not as prose to compose from memory.

Then, as separate sections built by *this skill* (not Granola) for task tracking: `## Attendees`, `## Action Items` (derived from the same content, checkbox format — see below), `## Decisions`, `## Context for LLM`. Because `## Action Items` restates content that's already verbatim in `## Notes`, don't present it as Granola's text — it's this skill's own derived task list.

## Action items → tasks (only for resolved clients)

**Hands off client deliverables.** Filing never sets `cu_task` on a card and never creates a task in a *client's* ClickUp list — deliverables are set deliberately by Zack or on explicit request (see the `clickup-deliverables` skill). If a meeting note looks like a client promise ("we'll have the October keyword research to Thankbox by Friday"), don't fulfil it: say so in the report (`looks like a Thankbox deliverable: create one?`) and let Zack decide.

Only when a client was confidently resolved — an action item with no client/project context is not a useful task. Each `- [ ] **Owner:** <name>` assigned to the user becomes a Kanban card.

- Prefer the single sanctioned writer: `/mnt/z/pantheon/vault/ZNH/scripts/vault_board.py upsert --title "..." --status open --priority <low|medium|high|critical> --assignees <owner> --client <client> --source granola --tags meeting-action`. Don't put `client/` or `src/` in `--tags` — the writer derives them from `--client` / `--source` (without `--source granola` the card is mislabelled `src/manual`).
- **Current board = TaskNotes** (`TaskNotes/Tasks/`, `pm-task: true` card files, live Bases view). There is NO project-level `taskIds` array anymore — scan card files on disk, never read-modify-write a stale index. See `reference/tasknotes-plugin-schema.md` in the obsidian skill.
- Unresolved-client notes: action items stay listed in the note body only, no card created.

## Notification

Both the webhook route and the cron job deliver **your final reply** to Slack; failures (crashes, timeouts) are delivered by Hermes itself. So:

- **Filed something** → final reply is a short summary: meetings filed (title + client), cards created, anything flagged `needs-triage` (name the meeting).
- **Nothing to do** (dedup-skip, unknown ID, batch run with no new meetings) → reply with exactly `[SILENT]` and nothing else.
- **Couldn't do the job** (Granola unreachable, OAuth expired) → fire the ntfy alert as above **and** say so plainly in the reply. Never `[SILENT]` on a failure.

## Verification

After filing, confirm each note exists under `Meetings/` and its `granola_id` is present in the state file's `seen_granola_ids`. Confirm created Kanban cards exist under `TaskNotes/Tasks/`. Run `uv run --no-project /mnt/z/pantheon/vault/ZNH/scripts/vault_tags.py check` and fix anything it reports for the files you wrote.
