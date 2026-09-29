---
name: delegated-run-verification
description: Confirm dispatched runs did real work before completion.
version: 1.0.0
platforms: [linux]
environments: [hermes]
metadata:
  hermes:
    tags: [dispatch, verification, no-op, completion, evidence, kanban, tasknotes]
---

# Delegated Run Verification — Exit 0 ≠ Work Done

## The core principle

A spawned agent run that ends with exit code 0 has NOT necessarily done
anything. Exit 0 means "the process ended without crashing". A no-op run —
session spawned, nothing written, no card transition, no completion record —
exits 0 cleanly and looks identical to a successful run in every log that
only records exit codes.

**Treat 0 as "not failed", never as "succeeded".** Completion claims require
artifacts, not exit codes.

## The failure signature (Pantheon / Obsidian TaskNotes board)

Card stuck `in-progress` with a blocker note reading:

    Hermes run exited 0 but never moved the card out of in-progress

(or variants containing "no completion evidence") = a **no-op dispatch**.
Nothing errored; a session was spawned, ended, and produced nothing.

Why the pipeline misses it: the `done` evidence gate in `vault_board.py`
only fires when something actually calls `vault_board.py complete`. A no-op
run never calls it, so no error surfaces — the card just strands silently.

Observed root causes (2026-08-03, two cards in this class):
- A Hermes middle-hop session spawned for a card that exited without
  executing the card's work (user diagnosis: "you launched sessions then
  exited, so no work actually happened").
- Required MCP mounts listed in `failed_mcps` at dispatch time (se-ranking,
  seocrawl were `connection_error`), stalling the run at the data-fetch step
  so it exited without writing anything.

## Handling a suspected no-op run

1. DO NOT treat exit 0 as success. DO NOT mark the card done.
2. Leave the card `in-progress` and refresh/keep the `blocker_reason` via
   `vault_board.py update --blocker-reason "..."`.
3. Diagnose the root cause: check MCP mount health (`pantheon mcp` status /
   hub `failed_mcps` list), check which routing leg spawned the session
   (was it a Hermes middle-hop for what was really a coding task?), check
   the assignee.
4. Fix the cause, then re-dispatch — the user deliberately re-queues the
   card through Ready for Agent (cards are NEVER created straight into
   ready-for-agent; `open` is the drafting lane and the move to
   ready-for-agent is the user's dispatch decision).

## Evidence that counts

Before accepting completion of a dispatched run, look for at least one of:

- VCS diff / committed changes in the working tree (`git status`, `git diff`)
- New or modified files at the expected location
- A card transition via `vault_board.py complete` (which itself is
  evidence-gated: PR URL, done Pantheon manifest, or a matching exit-0
  record in `~/.hermes/process-completions.jsonl`)
- Run output that shows actual tool activity (file writes, test runs), not
  just a plan

If none exist, the run was a no-op regardless of exit code.

## Reviewing a backlog: promote ready-for-review cards to done only on verified artifacts

When the user asks to "work the ready-for-review cards and move to done the ones
that are finished", treat it as an evidence-checking exercise, not a
bookkeeping pass. Dozens of cards can sit in ready-for-review; each needs a look
before promotion. Full back-to-back walkthrough: `references/ready-for-review-backlog-2026-08-16.md`.

### Workflow that held (16 cards, 2026-08-16)

1. **Enumerate**: `grep -rl "^status:.*ready-for-review" TaskNotes/Tasks/*.md` or
   `python3 scripts/vault_board.py list --status ready-for-review`.
2. **Do NOT trust `progress:` to decide done-ness.** A card at `progress: 0` in
   ready-for-review is commonly still complete — earlier feature/handoff cards
   promoted by the reaper never had progress bumped. Verified 2026-08-16: of 16
   cards, 5 were `progress:0` yet genuinely shipped (handoff template +
   vault_handoff.py, ccc-search Enter-close in main.js, ccc multi-column in
   styles.css, home-dashboard Search Console + API balances, vault-librarian
   table + trigger + history sidecar). Judge each against the ARTIFACT, never
   the progress field.
3. **Evidence that counts for a "done" verdict — concrete checks per kind:**
   - scratch-backed / code card: scratch dir exists, `.opencode-run.log` tail
     shows real output, AND the promised deliverable is on disk
     (`ls`/`grep` the output files, confirm generated JSON/CSV counts).
   - config/state card: the live state reflects the change, not just a log line
     (e.g. opencode `agents/*.md` exist; a `systemd` drop-in is present and the
     env var is set — `KANBAN_RUNTIME=herdr` verified via the drop-in file).
   - plugin / behavioural card: grep the shipped `main.js`/`styles.css` for the
     actual feature (Enter-close handler, `.ccc-search` two-column class),
     because progress:0 cards carry no run log at all.
4. **Promote through the single writer**, never hand-edited frontmatter:
   `python3 scripts/vault_board.py update --path "TaskNotes/Tasks/<card>.md" --status done --progress 100`
5. **Confirm zero remaining**: `vault_board.py list --status ready-for-review` → "0 cards".

### Speed without losing the exam

Batched `for` loops over the card list are fine, but keep the verification
meaningful: check the *kind-specific* artifact per card, not just "file exists".
The user reviews the ones you promoted AND the ones you left; a false `done` on
an unimplemented card erodes trust faster than a correct-but-slow pass.

## The idle-shell variant: dispatch "running" but opencode never spawned

A third way exit-0 (or "still running") lies: the DISPATCH SHELL is alive but
the intended CLI never launched at all. Verified 2026-08-16 on a dependency
audit via `opencode run` from `terminal(background=true, pty=true)`: `process
poll` reported `status: running` and herdr showed nothing, but `ps` under the
dispatch pid showed ONLY `zsh -l` with **no `opencode run` child** — opencode
had already bailed and dropped back to an idle shell prompt. No herdr entry,
no work, nothing.

Checklist when a background/PTY dispatch reports running but shows no activity:

1. **Look for the child, don't trust the shell.** `ps -eo pid,ppid,cmd | awk '$2==<dispatch-pid>'`
   — a bare `zsh -l` / login shell with no CLI child means the command already
   exited (or never ran) and the shell is just idling "running".
2. **Check the captured PTY log** — if it shows only the shell banner + cursor
   (e.g. a prompt line, no `> build · ` init banner), opencode never got far
   enough to print that banner.
3. **Root cause on this box: `--title` is not a valid `opencode run` flag.**
   Passing `--title "name"` (copied from `-f`-mode *commit* invocations in old
   logs) makes opencode 1.18.x bail at argument-parse time — before any model
   work or output. `opencode run` takes `--auto` and `-f/--file`; it does NOT
   take `--title`. Omit it.
4. **Fall back to foreground.** Foreground `opencode run --auto "..."` (with a
   generous `timeout 540`) worked reliably on the same machine/directory when
   every background/PTY variant died. For read-only investigations (dep audits,
   code reviews, searches) prefer foreground dispatch directly rather than
   burning turns retrying broken background variants.

## The hung-on-model-stream variant: process alive, CPU flat, no source writes

A run can be genuinely "running" (process alive, real CLI child present) yet
still produce nothing because it is blocked on an LLM model call that never
returns. This is distinct from the idle-shell variant (no CLI child) and the
continuation variant (work happening elsewhere): here the agent is up, streamed
a prompt to the model, and is waiting on a response that never arrives.

Verified 2026-08-16 on the Pantheon ntfy-notifier fix. A `opencode run` that had
already produced work (pre-existing source edits on disk) appeared stuck for 11
minutes. It had fired `message=stream providerID=synthetic modelID=hf:moonshotai/Kimi-K3`
and then gone completely silent.

Diagnostic checklist (cheap, read-only, no agent needed):

1. **Is it alive AND actually computing?** `ps -o pid,etime,%cpu,stat -p <pid>`,
   then sample accumulated CPU ticks twice ~2 s apart and diff:
   `awk '{print $14+$15}' /proc/<pid>/stat`. Flat across samples (a delta of a
   few ticks = milliseconds of work over seconds of wall time) combined with
   `State: S (sleeping)` on `ep_poll` = waiting on I/O/network (a hung model
   round-trip), not working.
2. **Do NOT take ".pyc written in the last 30 min" as progress.** The only
   recent file writes may be `.venv/**/*.pyc`, `.pytest_cache/*`,
   `.venv/bin/<pkg>` — the footprint of a single earlier test run, not ongoing
   work. Check the mtimes of the ACTUAL source files you expect it to be
   editing against when the process started (`ps -o lstart -p <pid>`). If those
   source mtimes predate the process start, the writes are a different/earlier
   run's work — this process hasn't touched them.
3. **Pin the exact stall moment from the logs.** `opencode.log` (e.g.
   `~/.local/share/opencode/log/opencode.log`) stamps every step with a
   `run=<uuid>`. Find the last `message=stream providerID=... modelID=<model>`
   line for that run — that is the model call currently in flight. If that
   timestamp is many minutes old and nothing has logged since, the call hung.
   Cross-check with `opencode.db`'s last-modify time (the session store): a
   `--format json` run's DB last-write should track the last stream. Silence =
   no work since.
4. **The stalled model is often an unpinned opencode DEFAULT.** When dispatched
   through the kanban board, `vault_kanban_dispatch.py`'s `_dispatch_opencode`
   herdr lane runs the plain `opencode run` with opencode's *own* default model
   — e.g. resolving to `synthetic/Kimi-K3`, which is NOT an explicit entry in
   `~/.config/opencode/opencode.json`'s provider `models` lists. The resolved
   model shows in the `> build · hf:...` banner and the log's `modelID=`. If the
   running default is one that has previously hung, pin a known-good model when
   re-dispatching rather than relying on the default.

**Action:** this is a stalled run, not a slow one. Do NOT wait it out — kill it
and re-dispatch (fresh scratch dir / fresh card per the re-dispatch sequence
below), pinning a model you have seen complete the same kind of task. Treat the
earlier `.pyc`/`pytest_cache` writes as signs of a prior test run, not liveness.

A companion walkthrough lives at `references/hung-on-model-stream-2026-08-16.md`.

## The wrong-content trap: re-dispatch re-runs the stale scratch dir + brief

A run can exit 0 AND write files AND still be wrong — because it executed the
**old** task brief for the **wrong** tool. This is the flip side of the no-op
trap and just as easy to confirm. Observed 2026-08-16 (Thankbox recipient
landing-page card): a first `opencode run` built a from-scratch copy generator
(the wrong approach; the dedicated tool existed at `github.com/Z-N-H/tb_child_lp_tool`).
It was killed, the card re-briefed to use the correct tool, and re-dispatched —
but the new run re-ran the OLD brief because the dispatcher silently reused
`scratch/015` and its stale `TASK-BRIEF.md`.

### Why re-dispatch silently repeats the old work

`vault_kanban_dispatch.py`:
- `_resolve_scratch_workdir` KEEPS an existing `scratch/NNN-<slug>` if present
  (same title/slug ⇒ same dir).
- `_find_or_write_brief` writes a fresh `TASK-BRIEF.md` only when none exists —
  so a corrected card with the same title re-runs the OLD brief in the OLD dir.
- `vault_board.py upsert` dedupes on `(source, source_id)`; a slightly-drifted
  `--source-id` (e.g. adding/omitting "card") creates a DUPLICATE `...-2.md`
  card instead of updating the original.
- A killed run leaves `blocker_reason: opencode run exited 143`.

### Correct re-dispatch sequence (verify each step)

1. **Delete the stale scratch dir first** so a fresh claim allocates a clean
   dir and writes the corrected brief:
   `pantheon scratch done NNN --force` (0-padded NUMBER, not the full dir name;
   `--force` skips the y/n prompt).
2. **Confirm the new dir's `TASK-BRIEF.md` actually contains your correction**
   before trusting the run:
   `grep -n "<correction-fragment>" scratch/NNN-*/TASK-BRIEF.md`
3. **Do not create a duplicate card** when re-briefing an existing one —
   reuse its EXACT `source_id` (or `vault_board.py update --path ...`). If you
   already created a duplicate, retire the stale file to
   `TaskNotes/Archive/<yyyy-mm>/` (no delete subcommand exists).
4. **Clear the stale blocker** and re-claim:
   `vault_board.py update --path ... --blocker-reason "" --status ready-for-agent`
   (the dispatcher re-claims `ready-for-agent` → `in-progress` automatically).
5. **Verify the run is actually using the intended tool**, not just "working":
   `grep -E "git clone|tb_child|<repo-or-tool>|<module-path>" scratch/NNN-*/.opencode-run.log`

The verification principle generalises: for ANY dispatched run, check not just
"did it write files" but "did it write files implementing the CURRENT brief
with the intended tool". Grep the run log for the tool/approach you specified.

## The continuation-process variant (exit 0 BUT work still running)

There is a second, subtler way exit-0 lies: the tracked run *did* exit cleanly,
but it only ran the first leg — OpenCode (or another CLI) spawned a
**continuation process with the SAME command line** that survives and finishes
the job, including applying DB migrations and verifying builds the `` tracked``
session never reached. Verified 2026-08-08 on a many-to-many schema migration:
the `notify_on_complete` ping fired with exit 0 and the PTY log frozen at
"Implementing now: migration first —", yet the live PocketBase already had the
new relation and all 16 categories applied, and `ps` showed a second
`opencode run` (identical command) still alive ~100s later.

Checklist when a tracked run reports done prematurely (schema/DB/build work):

1. **Is a continuation still alive?** `ps aux | grep -E "opencode run" | grep -v grep`
   — a second instance with the same command line means the job is STILL GOING.
2. **Verify the applied artifact on the live target, not just the file on disk.**
   For a migration: `curl` the backend record shape / collection count (e.g. the
   `categories` collection now has 16 rows with the renamed slug), confirm the
   migration file exists, and run the framework build. Files written ≠ applied.
3. **Do NOT eagerly re-dispatch** a second run because the tracked session exited
   mid-implementation — if a continuation is live you'll get two processes
   editing the same files (double-migration / double-write risk on a live DB).
   Give the continuation time, then re-verify. Re-dispatch only if nothing is
   alive AND the artifact is genuinely absent.
4. Only then accept completion or clear the blocker.

## The `pantheon task finish` gate: success criteria must be checked in the brief

Finishing a Pantheon task is itself evidence-gated. Verified 2026-08-16 on a
dependency-bump task: `pantheon task finish` refuses (exit 1) with
`Success criteria not yet verified` unless the task brief's
`## Success Criteria` checkboxes are `- [x]`.

**Fix:** edit `<task>-TASK-BRIEF.md`, flip each met `- [ ]` to `- [x]`, then re-run
`pantheon task finish`. Handle out-of-scope criteria HONESTLY rather than leaving
them blank: a criterion listed in the brief but excluded by scope (e.g. "align
hindsight client/server" when the scope forbade touching Hermes pins, where the
client lives) should be rewritten in the criterion text to record the deferral and
then checked — editing the text so the gate passes without misrepresenting the work.

**Before calling the gate met**, assemble the evidence the brief claims (typically):
`uv lock --check`, `uv sync --locked`, `uv run pytest`, a working `import`, and live
CLI version checks (`ccc version`, `nono --version`). Size/activate and log progress
via `pantheon task update --size <XS|S|M|L|XL> --status active` and
`pantheon task update --step "..." --progress N`. Let OpenCode do the actual edits;
never hand-edit `.pantheon/` or `main/`.

## Assignee-based routing direction (2026-08-03)

Dispatch logic should route on the card's `assignees` field:

- **Zack** → human task. Never auto-dispatch to any agent; the card is the
  record / notification.
- **Hermes** → research / low-level planning / analysis. Handled directly;
  the exit-0-no-op failure must be made structurally impossible (evidence
  gate on the run itself, explicit completion step, timeout + non-zero-exit
  handling).
- **OpenCode** → coding tasks go STRAIGHT to `opencode run --auto` with the
  card brief as the task prompt, bypassing any Hermes middle-hop that can
  exit early.

Design doc (investigation delegated to OpenCode 2026-08-03):
`docs/plans/dispatch-routing-by-assignee-plan.md` — verify actual location.

## Relationship to other skills

- `task-dispatch` (user-owned) — the full card protocol: vault_board.py as
  single writer, status flow, completion gate. Load for dispatch mechanics.
- `kanban` (user-owned) — Obsidian Operations board lifecycle, evidence
  gate details.
- `verification-before-completion` — the general iron law for own-work
  claims; this skill extends it to runs you dispatched.
- `opencode-worker` (user-owned) — how to spawn opencode correctly
  (`--auto`, workdir, PRD briefs).

If a user-owned skill above is wrong or outdated, recommend
`hermes curator adopt <name>` rather than editing it directly.

## References

- `references/exit-0-no-op-cards-2026-08-03.md` — the two affected cards
  (uids, briefs, timestamps), dispatch-time MCP fail state, the denied
  events-log read, and the investigation route.
- `references/ready-for-review-backlog-2026-08-16.md` — full 16-card
  ready-for-review → done backlog pass: which cards were scratch-backed vs
  progress:0 features, the artifact-check per card, and the `done` promotions.
