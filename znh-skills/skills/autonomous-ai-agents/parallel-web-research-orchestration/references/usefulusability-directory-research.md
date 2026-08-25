# Worked example — UsefulUsability directory research (2026-08-08)

A concrete multi-agent web-research orchestration. Use this as a reference
shape to reproduce (with modifications) for curated-directory/listing research.

## Deliverable contract

- Staging JSON only. Research agents do ZERO downstream writes. A human parses
  the staging file and ingests into the DB/CMS themselves.
- Gitignored workspace: `research/` with:
  - `tools.json` — structured staging file agents append to. Held a `meta`
    block documenting the field contract + enums + existing records.
  - `notes/` — free-form `.md` agent notes/memories/ideas.
  - `logos/` — downloaded brand logo assets (`logos/<slug>.<ext>`).
- Structured file stays strictly structured; free-form chatter goes in `.md`
  notes only.

## Fixed enums (baked into the brief)

- Categories → slugs: `user-testing`, `prototyping`, `analytics-heatmaps`,
  `surveys-feedback`, `accessibility`, `session-recording`.
- Pricing: `free` · `freemium` · `paid` · `free_trial`.

## Per-record required fields

`name`, `slug` (unique), `category`, `pricing`, `tagline`, `description`,
`website`, `logo` (relative path), `best_for`, `key_features` (array), `tags`
(array), optional `overview`; staging-only `status` (`draft`) etc.

## Verification workflow (every listed record)

find URL → visit official site → browse feature/product/pricing pages → log
fields from what was actually seen → download the logo. Drop any record that
can't pass a step (dead site, no real product, no pricing info, no logo).

## Tool routing used

- Tavily (web_search/web_extract) = discovery + extraction only.
- Playwright CLI = full browser for JS-heavy product pages.
- terminal = download the logo binary.
- SE Ranking (Pantheon MCP) = ORCHESTRATOR ONLY. Leaf agents cannot call it;
  the orchestrator pre-baked SERP/competitor candidates into briefs or supplied
  them on request. Subagents may not assume SE Ranking is in their toolset.
- ccc index (cocoindex) = orchestrator-owned re-index step so newly written
  research becomes semantically searchable. Snapshot, so must be re-run after
  agents land; agents must not assume their own just-written files are indexed.

## Pre-flight dedup (step 0 for every agent)

Load the authoritative inventory BEFORE researching: live REST endpoint of
existing records (e.g. `GET …/api/collections/tools/records?perPage=200`, public
read) + any sibling staging file. Build an `EXISTING` set; skip anything in it
including close-name variants. Orchestrator re-checks at merge. Prevents N
parallel agents converging on the same well-known tools.

## Dispatch split (6 categories, up to 5 agents)

- A1: user-testing
- A2: prototyping
- A3: analytics-heatmaps
- A4: surveys-feedback
- A5: accessibility + session-recording (pair the two smallest)

Every brief was self-contained, gave the absolute workspace path (subagents get
isolated working dirs — relative paths resolve wrong), the category + enum slug,
tool-routing rules, output contract, verification steps, quality bar, and the
"no downstream writes" rule.

## Post-run sequence

1. Merge per-category outputs into one `tools.json`; global dedup.
2. Re-run `ccc index` (from project root) so research is embedded/searchable.
3. Quality pass — drop/correct incomplete/duplicate/invalid records.
4. Verify valid JSON + contract compliance.
5. Report: counts per category, assets downloaded, agents re-directed, gaps,
   deliverable paths.

## Orchestration prompt boilerplate

A self-contained orchestration prompt was written so a FRESH session can
re-orchestrate with zero prior context. It contained: mission, read-first file
ordering, division of labour, dispatch plan, monitoring/driving behaviour,
post-run checklist, non-negotiables, deliverable path. Save such a prompt with
the brief when a multi-session run is expected.
