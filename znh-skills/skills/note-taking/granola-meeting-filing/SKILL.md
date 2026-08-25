---
name: granola-meeting-filing
description: File new Granola meetings into Obsidian as client tasks.
platforms: [linux]
environments: [hermes]
required_mcp_servers: [pantheon]
---

# Granola Meeting Filing

Pull NEW Granola meetings into the Obsidian vault at `/mnt/z/pantheon/vault/ZNH/`, matched to a client, with action items turned into Kanban cards. Runs inside a Hermes cron session spawned by the `granola-meeting-scanner` job.

## Trigger

The `granola-meeting-scanner` cron job invokes `hermes chat -q` with this skill loaded and passes the current `seen_granola_ids` in the prompt. The agent turn's job: fetch whatever is new, file it, append to state. See `docs/plans/2026-08-19-granola-meeting-scanner-design.md` for the architecture.

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

- Confident match → set `client:` and `related: [[Clients/<Client>]]`, tag the client slug.
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
tags: [meeting, granola, <client-slug or needs-triage>]
related:
  - "[[Clients/<Client>]]"          # omit if unresolved
```

`granola_url`: neither `get_meetings` nor `list_meetings` returns a link — construct it from the meeting UUID as `https://notes.granola.ai/d/<granola_id>` (Granola's known note URL scheme). Also add it as a clickable line right under the H1, e.g. `**Granola:** [Open in Granola](https://notes.granola.ai/d/<granola_id>)`, so it's visible without opening frontmatter.

**H1 title always includes the date**, matching the filename: `# <Granola title> — <date>` (em dash, same as the filename's separator — e.g. `# Thankbox SEO standing call — 2026-08-10`). Several meeting titles recur across weeks (standing calls, syncs), so the bare title alone doesn't disambiguate the note when it's open — the date must be there regardless of whether the title happens to be unique this time.

Body: `## Notes` is Granola's `summary` field **verbatim, in full — copy it as one block, do not retype, reword, re-head, reorder, or drop any part of it, including its own trailing "Next Steps" section.** This is the one part of the note that must read as Granola's own words, not this skill's. Do not normalize its formatting (leave escaped characters, curly quotes, etc. exactly as returned) — treat the fetched string as opaque, not as prose to compose from memory.

Then, as separate sections built by *this skill* (not Granola) for task tracking: `## Attendees`, `## Action Items` (derived from the same content, checkbox format — see below), `## Decisions`, `## Context for LLM`. Because `## Action Items` restates content that's already verbatim in `## Notes`, don't present it as Granola's text — it's this skill's own derived task list.

## Action items → tasks (only for resolved clients)

Only when a client was confidently resolved — an action item with no client/project context is not a useful task. Each `- [ ] **Owner:** <name>` assigned to the user becomes a Kanban card.

- Prefer the single sanctioned writer: `/mnt/z/pantheon/vault/ZNH/scripts/vault_board.py upsert --title "..." --status open --priority <low|medium|high|critical> --assignees <owner> --client <client> --tags <slug>`.
- **Current board = TaskNotes** (`TaskNotes/Tasks/`, `pm-task: true` card files, live Bases view). There is NO project-level `taskIds` array anymore — scan card files on disk, never read-modify-write a stale index. See `reference/tasknotes-plugin-schema.md` in the obsidian skill.
- Unresolved-client notes: action items stay listed in the note body only, no card created.

## Notification

Send **one Slack Block Kit summary** per run: meetings filed, action items → cards created, and anything flagged `needs-triage` (name the meeting). Use `send_message` with the same shape as the inbox-scanner digest.

## Verification

After filing, confirm each note exists under `Meetings/` and its `granola_id` is present in the state file's `seen_granola_ids`. Confirm created Kanban cards exist under `TaskNotes/Tasks/`.
