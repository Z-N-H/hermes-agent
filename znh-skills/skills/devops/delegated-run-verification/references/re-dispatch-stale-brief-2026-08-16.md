# Re-dispatch re-ran the stale brief — 2026-08-16 (Thankbox recipient LP)

Concrete reproduction of the wrong-content dispatcher trap, for reference.

## Scenario
1. Card `build-recipient-christmas-card-categorylanding-pages-25-recipients`
   (uid `Ri759q54`), a SCRATCH task to generate category/landing pages for 25
   Christmas-card recipients, dispatched to OpenCode.
2. First run built a **from-scratch** copy generator cloned from
   `scratch/004-gc-category-copy` — the wrong approach. The dedicated tool
   existed at `https://github.com/Z-N-H/tb_child_lp_tool` (a marimo app for
   child-page landing copy: occasion × recipient; SEO meta + hero + card grid
   + how-it-works + features; variations in `recipient|pronoun|relationship`).
3. Run killed (SIGTERM) → dispatcher recorded `blocker_reason: opencode run
   exited 143`.
4. Card re-briefed to use `tb_child_lp_tool`; re-dispatched.

## The failure
The re-dispatch ran the **old** brief. The scratch dir `015` was reused
(dispatcher `_resolve_scratch_workdir` keeps an existing matching
`scratch/NNN-<slug>`), and `_find_or_write_brief` only writes a fresh
`TASK-BRIEF.md` when none exists — so the new run read the stale one. The
working `TASK-BRIEF.md` at that point still said "reuse scratch/004" and did
NOT mention `tb_child_lp_tool`.

Additionally, re-briefing via `vault_board.py upsert` with a slightly-drifted
`--source-id` (`build-recipient-christmas-category-pages` vs the original,
which included "card") created a DUPLICATE card (`...-2.md`, uid `G6W3SA6F`)
instead of updating in place. Result: two cards for one task.

## Correct recovery (what landed)
1. `pantheon scratch done 015 --force` — deleted the poisoned dir, freed the
   number so a fresh claim allocates a clean dir.
2. Confirmed the re-allocated `scratch/015/TASK-BRIEF.md` contained the
   correction (`grep tb_child_lp_tool` line present).
3. Archived the stale duplicate card `Ri759q54` to
   `TaskNotes/Archive/2026-08/` (no delete subcommand in vault_board).
4. Cleared stale blocker + reset correct card:
   `vault_board.py update --path "...-2.md" --blocker-reason "" --status ready-for-agent`
5. Dispatcher re-claimed → `in-progress` (event log). Verified the new run
   log referenced `tb_child_lp_tool/znh_secrets.py` and the tool dir was
   present — i.e. it was actually cloning/using the intended tool.

## Dispatcher internals (task-dispatch/kanban are user-owned, this note is the
## curator-safe record)
- `_resolve_scratch_workdir(path, fields)` (vault_kanban_dispatch.py:344):
  reuses a pre-existing `scratch/NNN-<slug>`; else allocates next number.
- `_find_or_write_brief(workdir, fields, body)` (:368): reuses existing
  `*BRIEF*.md`, writes `TASK-BRIEF.md` only when absent.
- `vault_board.py upsert` idempotency keyed on `(source, source_id)`.

## Lesson
Trust nothing after a re-dispatch. Verify: (a) scratch dir was cleared so a
fresh brief was written, (b) the new `TASK-BRIEF.md` contains the correction,
(c) the run log shows the intended tool/clone. Check the run is "working"
≠ "working on the right thing".
