---
name: zight-transcript-filing
description: File a Zight (formerly CloudApp) screen recording's transcript into Obsidian as a client capture, with action items turned into Kanban cards.
platforms: [linux]
environments: [hermes]
required_mcp_servers: [pantheon]
---

# Zight Transcript Filing

Pull ONE Zight capture into the Obsidian vault at `/mnt/z/pantheon/vault/ZNH/`, matched to a client, with action items turned into Kanban cards. Runs inside the agent turn triggered by the `zight-transcripts` Hermes webhook subscription — one invocation per event, not a batch scan.

**REQUIRED:** Load `using-zight-mcp` before making any Zight MCP calls — it documents the confirmed `zight_get_transcript` schema, the `id`-not-`item_id` gotcha, and why the webhook payload's own `transcription` field must never be trusted directly.

**REQUIRED:** Load `vault-tagging` before writing any `tags:` — it defines `client/<slug>` / `src/zight` and the `vault_tags.py check` you run before finishing.

## Trigger and scope

The `zight-transcripts` webhook route only forwards `added_to_collection` events — Zight has one org-wide webhook URL firing every event type, and a route script (`zight_added_to_collection_filter.py`) already drops everything else before this skill ever runs. The payload you receive is the flattened `added_to_collection` payload (`item_url`, `name`, `item_type`, `collection_name`, `description`, `email`, `created_at`, plus a `type` field) — **ignore its `transcription` field entirely**; it can be an unresolved Ruby object's string form (`#<Transcription:0x...>`) rather than real text. Always fetch fresh via `zight_get_transcript`.

`added_to_collection` only fires for items actually added to a collection — if a capture is never collected, this skill never sees it. That's a property of the source, not a bug here.

## MCP availability precondition — check this FIRST, before anything else

This skill declares `required_mcp_servers: [pantheon]`, so a disconnected hub hard-fails the run before the first inference call — this section covers the failure the scheduler can't see from outside the hub: hub connected, but Zight unmounted / OAuth expired inside it. `pantheon mcp health` reporting Zight "healthy" only proves token validity, not that the tool actually works (see `using-zight-mcp`'s Troubleshooting table — this exact blind spot repeatedly broke the Granola integration silently).

Run `mcp__pantheon__search(query="zight")` before anything else. **If it returns zero `zight_*` tools, that IS the failure case** — treat it exactly like an explicit connection error. Do not fall back to browsing other tools, and do not file a note describing what you *would* have done. Fire an ntfy alert to topic `znh-pantheon` and end the run — a run that can't reach the tool it exists to call has no honest work to do.

## Fetching the transcript

1. Extract the item ID from `item_url` (last path segment — e.g. `https://share.zight.com/01a072d0-0ff6-753c-adb5-1651617e230f` → `01a072d0-0ff6-753c-adb5-1651617e230f`).
2. Call `zight_get_transcript` with `{"id": <extracted id>}` (see `using-zight-mcp` — NOT `item_id`).
3. If the transcript comes back empty or the fetch fails, wait ~30s and retry once — `added_to_collection` fires close to capture time and transcription processing may not have finished. If it's still empty after the retry, file the note anyway with `transcript-pending: true` in frontmatter and the raw `description` field as a stand-in, rather than blocking indefinitely or silently dropping the event.

## Idempotency

Before writing anything, check whether a note for this item already exists: search `Transcripts/*.md` frontmatter for a matching `zight_id`. If found, skip — this is a re-delivery (Hermes's webhook adapter has its own 1hr dedup window, but retries can land outside it), not a new capture. Never overwrite an existing capture note.

## Client matching

**Primary signal: `collection_name`.** Zight collections generally correspond 1:1 with clients — the user files recordings into a collection per client as a matter of habit, so the collection name is a stronger, more deliberate signal than free-text content. Match `collection_name` against `/mnt/z/pantheon/vault/ZNH/Clients/*.md` (filenames + aliases/brand/company names). A confident collection match wins outright — do not second-guess it against content signals, and do not require content to corroborate it.

**Fallback: content-based**, same approach as `granola-meeting-filing`. Use this only when `collection_name` is generic/non-client (e.g. `Test`, `Inbox`, `Uncategorized`, or any other collection that isn't a client name) or doesn't match any known client. Match `name`, `description`, and the fetched transcript content against the same `Clients/*.md` corpus.

- Confident match, from either signal → set `client:` and `related: [[Clients/<Client>]]`, tag `client/<slug>` (see `vault-tagging`).
- Low confidence or no signal from both → leave `client: ""`, tag `needs-triage`. **A wrong client silently attached is worse than an honest miss.**

## Writing the note

Flat `Transcripts/` folder (create it if it doesn't exist yet — Zight items are screen recordings/annotations, not meetings, so they don't belong in `Meetings/`). Frontmatter (uid via `/mnt/z/pantheon/vault/ZNH/scripts/vault_uid.py` scheme):

```yaml
uid: <8-char handle, vault_uid.py scheme>
type: capture
title: <Zight item name>
date: <created_at, date part>
source: zight
zight_id: <extracted item id>          # dedup key
zight_url: <item_url>
collection: <collection_name>
item_type: <item_type>                  # vi/video, sc/screenshot, etc.
client: <resolved or "">
transcript-pending: <true only if the retry in "Fetching" above still came back empty>
action-items-count: <n>
llm-context: "<short synthesized summary>"
tags: [capture, src/zight, <client/<slug> or needs-triage>]   # convention: vault-tagging skill
related:
  - "[[Clients/<Client>]]"              # omit if unresolved
```

**H1 title includes the date**, matching the filename: `# <name> — <date>`.

Body: `## Transcript` is the fetched transcript text verbatim (or, if `transcript-pending`, the payload's `description` field, clearly labeled as a placeholder pending the real transcript). Then `## Context` (collection, item type, Zight link), `## Action Items` (derived from the transcript, checkbox format, only for resolved clients — same rule as `granola-meeting-filing`).

## Action items → tasks (only for resolved clients)

**Hands off client deliverables.** Filing never sets `cu_task` on a card and never creates a task in a *client's* ClickUp list — deliverables are set deliberately by Zack or on explicit request (see the `clickup-deliverables` skill). If a capture looks like a client promise ("we'll have the October keyword research to Thankbox by Friday"), don't fulfil it: say so in the report (`looks like a Thankbox deliverable: create one?`) and let Zack decide.

Same sanctioned writer as every other vault automation — never hand-write card markdown:
```
/mnt/z/pantheon/vault/ZNH/scripts/vault_board.py upsert --title "..." --status open --priority <low|medium|high|critical> --assignees <owner> --client <client> --source zight --tags <topic-tags>
```
Unresolved-client captures: any action items stay listed in the note body only, no card created.

## Notification

The `zight-transcripts` route delivers **your final reply** to Slack; crashes and timeouts are delivered by Hermes itself. So:

- **Filed a capture** → final reply is a short summary: capture title, client resolution, cards created, `needs-triage` flag if applicable.
- **Duplicate (idempotency skip)** → reply with exactly `[SILENT]` and nothing else.
- **Couldn't do the job** (Zight unreachable, OAuth expired) → say so plainly. Never `[SILENT]` on a failure.

## Verification

After filing, confirm the note exists under `Transcripts/` with its `zight_id` set, and any created Kanban cards exist under `TaskNotes/Tasks/`. Run `uv run --no-project /mnt/z/pantheon/vault/ZNH/scripts/vault_tags.py check` and fix anything it reports for the files you wrote.
