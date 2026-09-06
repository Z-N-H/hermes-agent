---
name: kanban
description: "Hermes Kanban: orchestrator decomposition playbook + worker execution patterns, handoffs, and pitfalls."
version: 3.1.0
platforms: [linux, macos, windows]
environments: [kanban]
metadata:
  hermes:
    tags: [kanban, multi-agent, orchestration, routing, collaboration, workflow, pitfalls]
    related_skills: [opencode-worker, subagent-driven-development, hermes-agent]
---

# Hermes Kanban — Orchestrator & Worker Guide

> The core worker lifecycle is auto-injected into every kanban process via the `KANBAN_GUIDANCE` system-prompt block. This skill is the deeper playbook for both orchestrators (who plan and route) and workers (who execute).

## Task location: Obsidian board is the ONLY source — MANDATORY ROUTE

**THE canonical source for ALL task information is the Obsidian 🚀 Operations board, period. Not the filesystem. Not the Hermes Kanban CLI. Not git branches. Not TASK-BRIEF.md files. Nowhere else. Zero exceptions.**

This rule fires on ANY task-related query, not just "what open tasks do we have?":
- User says "try dispatching the task" → go to the Obsidian board, not the filesystem
- User asks about task status → Obsidian board only
- User wants to know what's pending → Obsidian board only
- User says "check what we're working on" → Obsidian board only

When ANY task-related question or directive appears, do NOT:
- Search the filesystem for TASK-BRIEF.md or project task directories
- Check `hermes kanban list` (that's the worker dispatch system, not the task board)
- List git branches, unmerged PRs, or `.task.json` files
- Scan scratch/, tasks/, or projects/ subdirectories for pending work
- Read filesystem TASK-BRIEF files — those are stale Pantheon artifacts, not active work

**The ONLY route:**
1. Read the cards directly under `vault/ZNH/TaskNotes/Tasks/*.md` — there is no separate board note anymore (TaskNotes replaced the old Project Manager board; the Kanban view is a live Obsidian Bases query, `TaskNotes/Views/kanban-default.base`, over this folder, not a plugin-private index)
2. Each card's YAML frontmatter carries `status` (`open`, `ready-for-agent`, `in-progress`, `ready-for-review`, or `done`), `priority`, `uid`
3. Report ONLY what the cards show. If the user follows up with "what else?" the answer is "nothing — that's everything on the board."

**Concrete mistake from this session (do not repeat):** The user said "try dispatching the task to opencode now" and the response went to the filesystem — searched for TASK-BRIEF.md files, read a task brief, and listed Pantheon task directories. The user immediately corrected: "why are you doing that? Tasks are explicitly from the kanban!!" and "yes, the obsidian kanban. That's the task location. Nowhere else." Do NOT reach for TASK-BRIEF.md files, project directories, or any filesystem artifact when the user mentions a "task."

**Hermes Kanban CLI** (`hermes kanban list`) is a separate worker-dispatch system. Its tasks are NOT the same as the Obsidian board's tasks. Do not mention or merge Hermes Kanban results into task-related answers.

## When to use the board

Create Kanban tasks when any of these are true:

1. **Multiple specialists are needed.** Research + analysis + writing is three profiles.
2. **The work should survive a crash or restart.** Long-running, recurring, or important.
3. **The user might want to interject.** Human-in-the-loop at any step.
4. **Multiple subtasks can run in parallel.** Fan-out for speed.
5. **Review / iteration is expected.** A reviewer profile loops on drafter output.
6. **The audit trail matters.** Board rows persist in SQLite forever.

If *none* of those apply — it's a small one-shot reasoning task — use `delegate_task` or answer directly.

## Step 0: Discover available profiles

Before fanning out, ground decomposition in the profiles that actually exist. The dispatcher silently fails to spawn unknown assignee names.

```bash
hermes profile list
```

Cache the result. Re-asking every turn wastes a tool call.

---

## Role 1 — Orchestrator: Decompose, Don't Execute

### Anti-temptation rules

- **Do not execute the work yourself.** If you find yourself "just fixing this quickly" — stop and create a task for the right specialist.
- **For any concrete task, create a Kanban task and assign it.** Every single time.
- **Split multi-lane requests before creating cards.** Extract independent workstreams, then create one card per lane.
- **Run independent lanes in parallel.** Leave them unlinked so the dispatcher fans them out. Link only true data dependencies.
- **Never create dependent work as independent ready cards.** Use `parents=[...]` in the original `kanban_create` call.
- **If no specialist fits, ask the user which profile to create or use.** Do not invent profile names.

### Decomposition playbook

**Step 1 — Understand the goal.** Ask clarifying questions if ambiguous.

**Step 2 — Sketch the task graph.** Draft the graph out loud before creating anything:
1. Extract lanes from the request.
2. Map each lane to a discovered profile.
3. Decide independence vs dependencies.
4. Create independent lanes as parallel cards (no parents).
5. Create synthesis/review cards with parent links to the lanes they depend on.

**Step 3 — Create and link.**

```python
t1 = kanban_create(
    title="research: Postgres cost vs current",
    assignee="<profile-A>",
    body="Compare infrastructure costs, migration costs, and ongoing ops over 3 years.",
)["task_id"]

t2 = kanban_create(
    title="research: Postgres performance vs current",
    assignee="<profile-A>",
    body="Compare query latency, throughput, and scaling at ~500GB, 10k QPS peak.",
)["task_id"]

t3 = kanban_create(
    title="synthesize migration recommendation",
    assignee="<profile-B>",
    body="Read T1 and T2 findings. Produce a 1-page recommendation with trade-offs.",
    parents=[t1, t2],
)["task_id"]
```

Children stay in `todo` until every parent reaches `done`, then auto-promote to `ready`. Create parent cards first, capture their ids, then include those ids in child `parents` lists.

**Step 4 — Complete your own task.** If you were spawned as a planner task, mark it done with a summary of what you created:

```python
kanban_complete(
    summary="decomposed into T1-T4: 2 research lanes in parallel, 1 synthesis, 1 prose draft",
    metadata={
        "task_graph": {
            "T1": {"assignee": "<profile-A>", "parents": []},
            "T2": {"assignee": "<profile-A>", "parents": []},
            "T3": {"assignee": "<profile-B>", "parents": ["T1", "T2"]},
            "T4": {"assignee": "<profile-C>", "parents": ["T3"]},
        },
    },
)
```

**Step 5 — Report back.** Tell the user what you created, naming actual profiles used.

### Common patterns

- **Fan-out + fan-in:** N research cards with no parents → one synthesis card with all as parents.
- **Parallel implementation + validation:** implementer + explorer in parallel, reviewer gated on both.
- **Pipeline with gates:** `planner → implementer → reviewer`. Each stage's `parents=[previous_task]`.
- **Human-in-the-loop:** Any task can `kanban_block()` to wait for input. Dispatcher respawns after `/unblock`.
- **Goal-mode cards:** For open-ended work, pass `goal_mode=True` to wrap the worker in a Ralph-style goal loop. After each turn, a judge checks acceptance criteria (title + body). Budget exhausted without completion → blocked for human review.

### Orchestrator pitfalls

- **Inventing profile names** → card sits in `ready` forever.
- **Creating tasks without assignee** → lands in `triage`, never dispatched.
- **Bundling independent lanes into one card** → misses parallelism.
- **Over-linking because of wording** — "also check X" does not mean X depends on the main task.
- **Pre-creating the whole graph when shape depends on intermediate findings** — let synthesis tasks plan their own children.

---

## Role 2 — Worker: Execute, Hand Off, Block, or Complete

### Workspace handling

| Kind | What it is | How to work |
|---|---|---|
| `scratch` | Fresh tmp dir | Read/write freely; GC'd when archived. |
| `dir:<path>` | Shared persistent directory | Other runs will read what you write. Path is absolute. |
| `worktree` | Git worktree | If `.git` doesn't exist, run `git worktree add <path> ${HERMES_KANBAN_BRANCH:-wt/$HERMES_KANBAN_TASK}` first, then cd and work normally. Commit work here. |

### Good handoff shapes

**Coding task:**
```python
kanban_complete(
    summary="shipped rate limiter — token bucket, keys on user_id with IP fallback, 14 tests pass",
    metadata={
        "changed_files": ["rate_limiter.py", "tests/test_rate_limiter.py"],
        "tests_run": 14,
        "tests_passed": 14,
        "decisions": ["user_id primary, IP fallback for unauthenticated requests"],
    },
)
```

**Review-required coding task:**
```python
import json

kanban_comment(
    body="review-required handoff:\n"
    + json.dumps(
        {
            "changed_files": ["rate_limiter.py"],
            "tests_run": 14,
            "tests_passed": 14,
            "decisions": ["user_id primary, IP fallback"],
        },
        indent=2,
    )
)
kanban_block(
    reason="review-required: rate limiter shipped, 14/14 tests pass — needs eyes on the user_id/IP fallback choice before merging"
)
```

**Research task:**
```python
kanban_complete(
    summary="3 libraries reviewed; vLLM wins on throughput, SGLang on latency",
    metadata={
        "sources_read": 12,
        "recommendation": "vLLM",
        "benchmarks": {"vllm": 1.0, "sglang": 0.87},
    },
)
```

Shape `metadata` so downstream parsers can use it without re-reading your prose.

### Claiming cards you created

Pass captured `kanban_create` return ids in `created_cards` on `kanban_complete`. The kernel verifies each id exists and was created by your profile. Never invent ids from prose or paste ids from earlier runs.

```python
c1 = kanban_create(title="remediate SQL injection", assignee="security-worker")
c2 = kanban_create(title="fix CSRF middleware", assignee="web-worker")
kanban_complete(
    summary="Review done; spawned remediations.",
    created_cards=[c1["task_id"], c2["task_id"]],
)
```

### Block reasons that get answered fast

Bad: `"stuck"`. Good: one sentence naming the specific decision you need. Leave longer context as a comment.

```python
kanban_comment(
    body="Full context: I have user IPs from Cloudflare headers but some users are behind NATs..."
)
kanban_block(
    reason="Rate limit key choice: IP (simple, NAT-unsafe) or user_id (requires auth, skips anonymous endpoints)?"
)
```

### Heartbeats

Good: `"epoch 12/50, loss 0.31"`, `"scanned 1.2M/2.4M rows"`. Bad: `"still working"`. Every few minutes max; skip for tasks under ~2 minutes.

### Retry diagnostics

If `kanban_show` shows closed prior runs, read their `outcome`:
- `timed_out` → chunk the work or shorten it.
- `crashed` → reduce memory footprint.
- `spawn_failed` → profile config issue; `kanban_block` to ask a human.
- `reclaimed` + `task archived` → check status carefully; you may not need to run.
- `blocked` → unblock comment should be in the thread.

### Worker Do NOTs

- Call `delegate_task` as a substitute for `kanban_create`. `delegate_task` is for short reasoning subtasks inside YOUR run; `kanban_create` is for cross-agent handoffs.
- Call `clarify` to ask the human a question. You are headless — the call times out (~120s). Use `kanban_comment` + `kanban_block` instead.
- Modify files outside `$HERMES_KANBAN_WORKSPACE` unless the body says to.
- Create follow-up tasks assigned to yourself — assign to the right specialist.
- Complete a task you didn't finish. Block it instead.

### Worker pitfalls

- **Task state changed between dispatch and startup.** Always `kanban_show` first. If `blocked` or `archived`, stop.
- **Workspace may have stale artifacts.** Read the comment thread for context on why you're running again.
- **Don't rely on CLI in containerized backends.** `hermes kanban <verb>` may fail in Docker/Modal. Prefer the `kanban_*` tools.

---

## Shared: Troubleshooting tasks that never start

**Task stuck in `triage` with no assignee.**
```bash
hermes kanban assign <task_id> <profile_name>
hermes kanban promote <task_id>   # triage → ready
```

**Dispatcher not running.**
```bash
ps aux | grep 'hermes.*gateway' | grep -v grep
hermes gateway run   # foreground, or install as service (non-WSL)
```

**Verify task is running:**
```bash
hermes kanban show <task_id> --json | python3 -c "import sys,json; t=json.load(sys.stdin)['task']; print(f'Status: {t[\"status\"]}, Assignee: {t[\"assignee\"]}')"
```

Lifecycle: `triage` → `ready` → `running` → `done` / `blocked`. Only `ready` + assigned tasks get dispatched.

## Recovering stuck workers

Three primary actions from the dashboard or CLI:
1. **Reclaim** (`hermes kanban reclaim <task_id>`) — abort the running worker and reset to `ready`.
2. **Reassign** (`hermes kanban reassign <task_id> <new-profile> --reclaim`) — switch to a different profile.
3. **Change profile model** — edit `~/.hermes/profiles/<name>/config.yaml`, then reclaim.

## Notification routing

## TaskNotes Operations board card lifecycle

When using the TaskNotes-backed Operations board (not the Hermes Kanban), card state is tracked entirely via YAML frontmatter in the card file under `TaskNotes/Tasks/`. **All card writes go through `vault_board.py`** — it is the single writer. There is no board note and no `taskIds` array to keep in sync anymore (that bookkeeping existed only for the old Project Manager plugin, whose whole-project cache could silently revert external writes); the Kanban view is a live Obsidian Bases query over the `Tasks/` folder, so a card's own frontmatter *is* the board state. Writes happen under a writer lock, with an append-only audit trail in `TaskNotes/.board-events.jsonl`. Hand-editing card frontmatter with `write_file`/`patch` skips that lock and is vetoed for `status: done` by the `task_completion_guard` plugin. `audit_board()` repairs drift (stuck-in-progress cards, unparseable cards, unevidenced `done`) at scanner startup and in daily maintenance.

### Card state transitions

Status is one of exactly five values: `open` (drafting area, never auto-dispatched), `ready-for-agent`, `in-progress`, `ready-for-review`, `done`. There is no separate `blocked`/`cancelled` status — a stuck or stalled card just stays in whatever status it's in and gets a `blocker_reason` frontmatter note instead.

| Action | How | Who does it | Side-effect |
|--------|-----|------------|-------------|
| Queue for an agent | Drag card to **Ready for Agent** | User | Watcher dispatches it |
| Dispatch work | `vault_board.py` claim (ready-for-agent → in-progress) | `vault_kanban_dispatch.py` | Event logged |
| Work completes | `vault_board.py complete` (evidence-gated) | Agent | Event logged; Slack DM if the watcher dispatched the card |
| Needs input / stuck | `blocker_reason` set via `vault_board.py update` (status stays as-is) | Agent/user | Shows in daily note "Needs your input" |
| Manual close | `vault_board.py complete --force` | User | Logged as manual override |

### The evidence gate

`vault_board.py` refuses `status: ready-for-review` (agent completion) or `status: done` (human promotion via this module) without independent proof of completed work: a PR on the card, a done Pantheon manifest, or a recent exit-0 record in `~/.hermes/process-completions.jsonl` matching the card. Refusals are logged. If you can't point at completed work, leave the card `in-progress` with a `blocker_reason` — never `--force` your way past the gate.

### Pitfall: avoid the completion-marker pattern

Do not write `.pending`/`.done` marker files under `.hermes/task-completions/`. That design was deprecated because the markers live outside the vault and don't trigger the file watcher — they sit unprocessed until the next Kanban card edit happens. Use `vault_board.py` instead. See the `task-dispatch` skill for the protocol.

Configure cross-profile notifications in `~/.hermes/config.yaml`:
- `notification_sources: ['*']` — all profiles.
- `notification_sources: ['default', 'zilor-ppt']` — restrict to listed profiles.
- Omitting the key keeps profile isolation.

## Related Skills

- `opencode-worker` — If the worker profile mandates all code changes go through OpenCode CLI.
- `subagent-driven-development` — For parallel review during implementation (complementary to Kanban's cross-agent handoffs).
- `hermes-agent` — Gateway setup, spawning, CLI reference.
