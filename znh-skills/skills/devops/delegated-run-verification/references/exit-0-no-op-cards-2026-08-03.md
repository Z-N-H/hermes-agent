# Exit-0 No-Op Cards — 2026-08-03 Session Detail

## The two affected cards

Both were claimed `in-progress` by the dispatcher, a run was spawned, and
nothing happened. Each carried the identical blocker note:

    Hermes run exited 0 but never moved the card out of in-progress

| Card | uid | status | assignees | last updated |
|------|-----|--------|-----------|--------------|
| Bulk christmas cards for Thankbox | S4tnDmt3 | in-progress, progress 0 | OpenCode, Hermes | 2026-08-03T10:20:45Z |
| Thankbox new page optimisation | IYQq1TKE | in-progress | Hermes | 2026-08-03T10:26:24Z |

## Context at dispatch time

Hub status showed the MCP mounts both tasks depended on in `failed_mcps`:

- se-ranking → `connection_error`
- seocrawl → `connection_error`

So even a well-behaved run would have stalled at the data-fetch step.
Separately, the user diagnosed the primary cause: "you launched sessions
then exited, so no work actually happened" — a spawned Hermes session that
never executed the card's work.

## Task briefs (what the cards required)

1. **Bulk christmas cards** — seed keywords (bulk christmas cards, corporate,
   wholesale, personalised-in-bulk, staff-gifting angle), exact-match volume
   via SE Ranking `exportKeywords` (uk+us, NOT `getSearchVolume`), related/
   similar keyword expansion, difficulty+CPC, seasonality caveat, deliverable
   was a Marimo notebook for review. Card created 08:17Z, originally
   ready-for-agent, corrected to `open` same morning (user rule: never create
   cards at ready-for-agent), later deliberately dispatched and renamed by
   TaskNotes to "Bulk christmas cards for Thankbox".
2. **Thankbox new page optimisation** — SEOcrawl to grab optimisable
   keywords for /cards and /gift-cards category pages (non-brand, rank 2-20),
   SE Ranking supplementary, Marimo analysis with 1 primary + 5 secondary
   keywords per page; run scope was /gift-cards subdirectory only.

## Investigation route

- Read the two card files (frontmatter + body) from disk.
- Attempt to read `TaskNotes/.board-events.jsonl` first: terminal command
  DENIED by user — the events log was off-limits; read of
  `~/.hermes/process-completions.jsonl` was acceptable. Base failure
  analysis on code paths + card frontmatter instead.
- Delegated full pipeline investigation (trigger_scanner.py,
  vault_kanban_dispatch.py, vault_board.py, gateway spawn sites) to OpenCode
  as read-only + one design doc:
  `docs/plans/dispatch-routing-by-assignee-plan.md`.

## Outcome

Both cards left stranded in-progress with the blocker note intact. Re-dispatch
was deferred pending the routing design; user must deliberately re-queue
through Ready for Agent per the standing rule.
