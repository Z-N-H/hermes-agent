---
name: vault-triage
description: Classify a vault note and act on it — file it, card it, answer it, or park it for Zack. Auto for the obvious, ask for the ambiguous.
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [obsidian, vault, triage, inbox, filing, kanban]
    related_skills: [obsidian, vault-lookup-by-uid]
---

# Vault Triage

The vault is Zack's internal knowledge base and internal PM layer. He writes
most notes himself, fast and unstructured. Your job is to sort them: file what
is obvious, track what is actionable, and **ask about what isn't clear** rather
than guessing.

You are called with one note at a time (from the watcher/trigger system), or
multiple notes in a single session (from the inbox-scanner cron runner). When
invoked with multiple notes, process each one independently — read, classify,
act, and stamp *before* moving to the next. Always reference the `triage:`
state of each note to skip ones already handled.

Each note has already been left alone for two minutes since its last write
(by the timer or settle check), so it is not half-written.

## The governing rule

> Confident → act. Not confident → make a card and ask.

Filing a client note into the wrong folder is cheap to undo. Silently
mis-summarising a client decision into Hindsight is not — it becomes context
that misleads every later conversation. When in doubt, park it.

Never delete a note. Never rewrite Zack's prose. You add frontmatter, add links,
and move files. That's it.

## Step 1 — Read it

Read the full note. If it references a uid, resolve it first
(`vault-lookup-by-uid`) so you're classifying with the context, not without.

**Before classifying a client-related note, read `Clients/Clients.md`**
to check whether the client is known and what directory they use. If the
client isn't listed, add them to the table when you file the note.

## Step 2 — Classify

### A. Reference / knowledge — HIGH confidence only

Clear client information, a decision with its rationale, research findings,
meeting outcomes. You can tell *which client or project it belongs to* and
*what kind of note it is*.

Do all of:

1. Move it to the right folder:
   `Clients/<Name>/`, `Decisions/`, `Research/`, `Meetings/`, `Projects/`,
   `Operations/`, `Braindumps/`
2. Add frontmatter matching the **live** convention (kebab-case, not the
   older snake_case in `Schemas.md`):
   ```yaml
   type: research          # client | project | decision | meeting | research | note | braindump
   title: ...
   date: YYYY-MM-DD
   status: active          # the DOCUMENT's lifecycle — never the triage state
   client: ...             # when it belongs to one
   tags: [...]
   llm-priority: medium    # low | medium | high
   llm-context: "One sentence: what an agent needs to know about this note."
   related:
     - "[[Some Other Note]]"
   ```
   Leave `uid:` alone — it's already there and it's the note's address.
3. `hindsight_retain` the substance, with tags from: `client`, `decision`,
   `research`, `reference`. Include the note's uid in the memory text so the
   memory points back at its source.
4. Set `triage: done`. Leave `processed_at`/`processed_hash` alone — the
   runner writes those itself, with a real clock.

If you cannot confidently name the client/project or the note type — this is
**not** category A. It's category D.

### B. Action item

The note asks for something to be done, by Zack or by you.

**Pick the assignee by what kind of work it is** — this is what decides
which lane `vault_kanban_dispatch.py` routes the card through once it
reaches Ready for Agent, so getting it right here is what makes dispatch
actually work instead of stalling silently:

- **Coding/implementation task** — the deliverable is a code change (fix a
  script, change how something renders, add a flag, build a feature) →
  `--assignees "OpenCode"`. This is the deterministic lane: the dispatcher
  runs `opencode run` itself, synchronously, no LLM hop and no approval
  gate in the way.
- **Non-technical action item** — a call to make, a decision, a client
  follow-up, nothing an agent can code its way out of → `--assignees
  "Zack"`.
- **Do not assign `Hermes` to a coding task** just because triage is the
  one creating the card. A `Hermes`-assigned coding task routes through
  the one-shot research lane, which can't make the code change itself —
  it tries to background-spawn `opencode run` from inside its own sandboxed
  terminal instead. That spawn needs manual approval it cannot get while
  running unattended, so it stalls, times out, and leaves the card blocked
  with zero work done (`blocker_reason: "Hermes run exited 0 but never
  moved the card out of in-progress"` — this is exactly what happened to
  card `feenQnpz`, "Better herdr output formatting", 2026-08-22). If the
  note genuinely needs research or analysis rather than a code change,
  `Hermes` is the right call — see category F.

1. Create a card:
   ```bash
   python3 /mnt/z/pantheon/vault/ZNH/scripts/vault_board.py upsert \
     --title "<short imperative title>" \
     --status open \
     --source hermes-triage \
     --source-id "<note uid>" \
     --assignees "OpenCode" \
     --note "[[<note filename without .md>]]" \
     --client "<client if any>" \
     --due "YYYY-MM-DD"
   ```
   (`--assignees "Zack"` instead, for the non-technical case above.)
2. Set `triage: done` and `type: task` on the note.
3. Don't move it yourself — `type: task` files it to `Tasks/` automatically.
4. **Dispatch the implementation immediately** (interactive sessions only). If you're in an active conversation with Zack (not a cron triage run) and the card is assigned `OpenCode`, do not stop at card-creation — move it straight to Ready for Agent yourself: `vault_board.py update --path "<card path>" --status ready-for-agent`. That's what actually triggers `vault_kanban_dispatch.py`'s OpenCode-direct lane; don't just say you'll "dispatch it" without making that call. Zack's expectation is that a triaged coding card gets worked on, not just filed. A past session created a card for "Wire ccc embeddings into Obsidian search" and then never dispatched the implementation — the card sat on the board as a todo with no work ever started. Avoid this by moving OpenCode-assigned cards straight to Ready for Agent when in an interactive session.

**Never write card markdown by hand.** `vault_board.py` is the single sanctioned
writer — it handles the uid, the writer lock, and the audit trail
(`TaskNotes/.board-events.jsonl`). Hand-written cards have reliably desynced
the board (missing uids, malformed frontmatter TaskNotes won't recognise).

### C. Reminder / time-bound follow-up

"Remind me to email Sam tomorrow", "chase the invoice on Friday", "voicenote
Maria at 5.30".

**These go to ntfy, not ClickUp and not the vault board.** ntfy is a single
authenticated HTTP POST straight to Zack's phone. It has no assignee semantics
to get wrong, no schema to reject you, and no socket to be disconnected. It is
one shell command:

```bash
pantheon notify send "<the reminder>" \
  --title "⏰ <short imperative>" \
  --priority 4 \
  --tags alarm_clock \
  --at "2026-08-05 09:00"
```

`--at` schedules delivery **server-side**, so the reminder survives this process
exiting. It accepts `"30m"`, `"3h"`, `"tomorrow, 10am"`, `YYYY-MM-DD HH:MM`, or
a Unix timestamp. ntfy.sh caps scheduling at **3 days out** — for anything
further away, create a ClickUp task instead and say so in your report.

The command **exits non-zero if delivery fails**. Check it. If it fails, do not
mark the note done — report the failure, with the command's output, in Step 4.

**ClickUp is opt-in now, not the default.** Use it only when the note explicitly
asks for it ("put this in ClickUp", "add to my ClickUp list") or when the
reminder is more than 3 days out. When you do, the call is unchanged:

```python
await call_tool(
    "clickup_clickup_create_task",
    {
        "name": "<short imperative>",
        "list_id": "901219884344",  # Personal > General > Reminders
        "due_date": "YYYY-MM-DD HH:MM",  # this exact format — epoch ms is rejected
        "assignees": ["me"],  # unassigned tasks notify nobody
        "priority": "high",  # urgent|high|normal|low — words, not numbers
        "markdown_description": "From vault note `<uid>` — <title>.\n\n> <the line that prompted it>",
    },
)
```

Both format notes are from real rejections — `due_date` must match
`YYYY-MM-DD( HH:MM)?` and `priority` must be one of those four words.

**Never park a reminder as category D.** If the timing is vague ("remind me to
test ClickUp", no date), still send it — pick a sensible default (tomorrow 09:00
for "soon", today 17:00 for "later today") — and *then* message Zack to confirm
the time. A reminder with a slightly wrong time is a minor annoyance; a reminder
that was never created is a missed commitment. This has already happened twice:
once a note was parked as `draft` asking which time, and once (`uid: upiWpomj`,
2026-08-03) the agent ran terminal commands instead of creating anything at all,
hit a denied command four minutes after the target time, and wrote an excuse
into `llm-context` rather than reporting the failure.

Always reference the source note's `uid` in the message body so the reminder can
be traced back.

Then set `triage: done` and `type: reminder` on the note (which files it to
`Tasks/`). **Do not create a vault card** — a personal reminder has no internal
breakdown, no notes and no agent work attached, so a card would just be a second
copy of the same line showing up in the daily note.

**Do not use `cronjob` for reminders.** It was tried and it is the wrong tool:
a one-shot job that fails is consumed and gone with no retry and no warning,
and its default `deliver="origin"` resolves to nothing when triage runs from a
short-lived CLI process. Cron is for recurring *work*, not for nudging a human.

#### Which channel for which message

| Kind of message | Channel |
|---|---|
| Reminders, alerts, task completions, failures | **ntfy** (`pantheon notify send`) |
| Questions, clarifications, anything needing Zack's context back | **Slack** (tag him) |
| Reminders more than 3 days out, or when the note names ClickUp | **ClickUp** |

The split is about whether a reply is expected. ntfy is one-way — it interrupts
but cannot carry a conversation. If you need an answer, use Slack.

### D. Ambiguous — needs Zack

You're not sure what it is, who it's about, or what he wants. This is the
default when confidence is low. **Do not move the note.**

1. Create a Triage card:
   ```bash
   python3 /mnt/z/pantheon/vault/ZNH/scripts/vault_board.py upsert \
     --title "Triage: <note title>" \
     --status open \
     --source hermes-triage \
     --source-id "<note uid>" \
     --note "[[<note filename>]]" \
     --body "$(cat <<'EOF'

# Triage needed

**My reading:** <what you think this is>

**Where I'd put it:** <proposed folder + type>

**What I need from you:** <the specific question>

EOF
)"
   ```
2. **Message Zack on Slack. This is mandatory, not optional.** Use
   `send_message` with your interpretation and the specific question.
3. Set `triage: parked` on the note so it isn't re-triaged.

`parked` is a **terminal** state — the note will never be re-triaged. If
you park something without telling Zack, the request is dead and he will find
out by missing a deadline. The card persists for later reference; the Slack
message is what actually reaches him.

The triage runner sends a Slack DM automatically whenever a note ends up
`parked`, as a backstop. Don't rely on that and skip your own message — the
backstop only has the note's frontmatter to work from, so it can restate the
question but not your reasoning.

**Prefer acting to asking.** Category D is for things where a wrong guess would
be genuinely costly — filing to the wrong client, misattributing a decision.
For anything recoverable, make your best call, do it, and tell Zack what you
assumed. Asking has a real cost: it stops the work and puts it on him.

### E. Question for you

The note asks you something directly that expects a concrete answer
("Hermes, what's the status of X?", "When was Y note written?", "What
does this error mean?").

1. Answer it using your tools — Hindsight recall, vault lookup, web search.
2. Append the answer to the note under `## Response`, dated.
3. Set `triage: done`.

**Trap — this is NOT category E:** If the question is about what could be
built, explored, or changed ("What would be useful to add?", "What do you
think about X feature?"), it's a discussion starter, not a lookup. Use
**category F (Feature request / brainstorm)** instead — card it, don't
answer it inline.

### F. Feature request / brainstorm / discussion starter

The note proposes an idea, asks "what would be useful?", or opens a
discussion about something to build or change. It may look like a question
but it's not expecting a one-shot answer — it's an invitation to explore.

**Do NOT answer inline.** Do not write a `## Response` section with your
analysis. The note is the prompt; the card is where it lives.

**Assignee follows the same rule as category B.** If the idea, once named
as an imperative title, is really a concrete code change (a feature, a
formatting fix, a behaviour change) → `--assignees "OpenCode"`, not
`Hermes` — same reasoning as category B: a `Hermes`-assigned coding task
stalls behind a manual-approval gate it can't clear unattended instead of
getting done. Reserve `Hermes` for ideas that need open-ended research or
discussion before any code gets written. When genuinely unsure which it
is, default to `Hermes` — category F exists for things still being
explored, not committed work.

1. Create a card on the Operations board:
   ```bash
   python3 /mnt/z/pantheon/vault/ZNH/scripts/vault_board.py upsert \
     --title "<short imperative title based on the topic>" \
     --status open \
     --source hermes-triage \
     --source-id "<note uid>" \
     --assignees "OpenCode" \
     --note "[[<note filename without .md>]]" \
     --body "$(cat <<'EOF'

# <topic>

<2–3 line summary of what the note proposes>

Source: [[<note filename>]] (uid <uid>)
EOF
)"
   ```
2. Set `triage: done` and `type: task` on the note.
3. The note files to `Tasks/` automatically via `type: task`.
4. Offer to start working on it (interactive sessions only).

**Trap:** A note that asks "What do you think about X?" or "Would it be
useful to add Y?" looks like category E. It is not. A direct question
expects a concrete, deliverable answer (facts, status, lookup). A question
about what could be built or explored is a discussion starter — card it,
don't answer it.

### G. Stub / gibberish

Under ~30 meaningful characters, or no actionable content. Set
`triage: discarded`. Do nothing else. Say nothing.

## Step 3 — Say where it goes

**The Inbox is a queue, not a shelf.** Every note you finish leaves it; the
runner does the move, you just say where.

- Moved it yourself (category A)? Nothing more to do.
- Otherwise set `dest:` to the folder it belongs in — `Research`,
  `Clients/Acme Corp`, `Operations`, and so on. It must be a folder that
  already exists.
- `type: task` or `type: reminder` routes to `Tasks/` without a `dest:`.
- No `dest:` and no task type falls back to `Braindumps/`.
- `triage: parked` is the one state that stays put. That is the signal — a
  note in the Inbox means it is waiting on Zack, and nothing else.

Prefer a real folder to the fallback, but don't agonise: every note keeps its
uid, so a wrong folder is one `vault-lookup-by-uid` away from being fixed. An
Inbox that never empties is not.

## Step 4 — Report

Reply with one line per action actually taken. Nothing else — no preamble, no
restating the note.

```
filed    Acme pricing feedback -> Clients/Acme Corp/  (hindsight: client, reference)
carded   Chase UOWN invoice     -> open, due 2026-07-30
triage   Broken contex          -> needs your call: which project?
```

If you took no action, say `no action: <why>` in one line.

Only send a Slack message when something genuinely needs Zack's attention
today — a category D question or a failed action. Routine filing does not
warrant a ping; it shows up in the daily note. The 2-minute Slack drumbeat this
replaced was noise he learned to scroll past, which defeated the point.

## The `triage:` lifecycle

You own `triage:`. The watcher reads it to decide whether to look at the note
again:

| Value | Meaning | Re-triaged? |
|---|---|---|
| *(absent)* | never seen | yes |
| `done` | handled | only if Zack edits the body afterwards |
| `parked` | awaiting Zack | never |
| `discarded` | stub, ignored | never |

**`triage:` is not `status:`.** `status:` belongs to the note — Kanban cards use
`open`/`ready-for-agent`/`in-progress`/`done`, decisions use `proposed`/`accepted`, documents use
`active`/`final`/`draft`. Triage used to share that field, and it cost real
data: a reference note carrying `status: active` was re-triaged on every touch
forever, and this skill's own category-A template said `status: draft`, which
the runner read as "parked awaiting Zack" and never revisited — silently
retiring notes it had just filed correctly. Write `triage:`; leave `status:`
to mean whatever it means for that kind of note.

Do **not** write `processed_at:` or `processed_hash:`. The runner writes both
itself after a successful run, because the model gets clocks wrong — one run
stamped `15:33+01:00` for a write that happened at `16:30 UTC`. Freshness is
decided on a hash of the body, not on timestamps.

Pitfalls

- **Don't re-file something already filed.** If the note has a `type:` and
  sits outside `Inbox/`, Zack has already placed it. Add missing frontmatter
  and links; don't move it.
- **Don't invent clients.** If the client name isn't in `Clients/`, it's
  category D, not a new folder.
- **Don't retain low-value memories.** "Zack wrote a note about testing" is
  noise. Retain substance or nothing.
- **One note, one pass.** You are invoked per note (watcher path) or given a
  batch in a single session (cron path). In either case, only act on the notes
  you were given — don't go hunting through the rest of the inbox.
- **`vault_board.py` upsert requires `--source` and `--source-id`.** Calling `vault_board.py upsert` with only `--title` and `--status` without specifying `--source` and `--source-id` will create duplicate task files (e.g. `<slug>-2.md`). To update an existing card's status, pass its exact `--source` and `--source-id` or edit `status:` directly in its markdown file under `TaskNotes/Tasks/`.
- **Always write `triage:` frontmatter.** If you complete a triage but don't
  write `triage: done` (or `parked`/`discarded`), the runner treats exit 0 as
  failure — the note stays eligible for re-triage and eats the budget on every
  cycle. Verify your output includes a valid `triage:` state before finishing.
