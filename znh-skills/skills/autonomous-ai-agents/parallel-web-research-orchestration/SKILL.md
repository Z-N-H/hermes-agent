---
name: parallel-web-research-orchestration
description: Run parallel web research subagents to one dataset.
version: 1.0.0
platforms: [linux, macos, windows]
environments: [hermes]
metadata:
  hermes:
    tags: [research, subagents, orchestration, delegate_task, parallel, curation]
    related_skills: [dispatching-parallel-agents, subagent-driven-development]
---

# Parallel Web-Research Orchestration

Manage a small team of web-browsing research subagents to turn broad discovery
into one curated, verified, structured dataset. You are the PM: dispatch,
monitor, push quality, merge, verify. You do NOT do the research yourself and
you do NOT write the deliverable — you orchestrate.

Use when the ask is "research a set of things across many categories/domains
and produce a structured dataset to hand to a human" — e.g. building a curated
directory, gathering tool/product listings, competitor sweeps, market surveys
with per-entity structured records.

> **Distinct from `dispatching-parallel-agents` / `subagent-driven-development`:**
> those parallelize CODING/implementation work in Pantheon worktrees with
> merge-to-parent code integration. THIS skill parallelizes WEB RESEARCH that
> lands as *data files* (JSON/MD), with the orchestrator owning data-layer /
> MCP-gated tools. Do not confuse the two.

## Core Principle

Split the domain into independent units (usually categories), assign one
subagent per unit, cap concurrency, and have each subagent write its own
structured output into a shared, gitignore-able workspace. Orchestrator merges
+ dedupes + quality-gates at the end. The orchestrator keeps every request
self-contained (subagents have zero memory of your conversation) and actively
drives agents, rather than fire-and-forgetting.

## The Shape It Needs Before Anything Runs

This class of task usually needs a **written brief/spec first** (so agents and
the human share one contract). Before dispatching, confirm or write:
- The **fixed enums** (allowed categories, pricing/status values) — so agents
  can't invent new ones.
- The **per-record required fields** and a **staging JSON shape**.
- The **verification workflow** each record must pass (for web research: find
  URL → visit site → browse feature/pricing pages → log from what you saw →
  download any binary asset like a logo).
- **Explicit tool-access routing** — which tools the leaf agents have vs which
  only the orchestrator can call (see Division of Labour).
- A **handoff contract**: agents write structured data to a file; the
  orchestrator does NOT push to the downstream store (DB/cms); a human ingests.

Save the brief to `docs/plans/` AND keep a copy in the research workspace so a
fresh session can re-orchestrate from it.

## Division of Labour (the single most important rule)

**Orchestrator owns:**
- Any **MCP-gated / externally-credentialed data tools** (SE Ranking, Pantheon
  MCP hub, keyword tools). Leaf subagents CANNOT call these — route them: you
  either pre-bake the SERP/competitor candidates into each agent's brief before
  dispatch, or supply results on request mid-run.
- The **pre-flight inventory** (already-known items used for dedup).
- **Merging** per-unit outputs, **global dedup**, final **quality pass**.
- Any **re-index / embedding** step (e.g. re-running `ccc index` so newly
  written research is semantically searchable).
- **Monitoring + driving** the team.

**Each leaf subagent owns:**
- Its assigned category/unit.
- **Discovery**: web search (Tavily by default), directories (G2, GetApp,
  Capterra, Product Hunt).
- **Full-site verification** using a real browser (Playwright CLI for JS-heavy
  pages) + terminal.
- **Downloading binary assets** (logos/images) via terminal.
- Writing its structured output + free-form `.md` notes.

## Tool-Access Routing Cheat-Sheet

- **Tavily / web_search / web_extract** = discovery + extraction only. Cannot
  render JS pages or download binaries.
- **Playwright CLI** = use when a full real browser is needed to read a page.
- **terminal** = download the binary logo/image file.
- **SE Ranking / Pantheon MCP** = orchestrator only, NOT leaf agents.

## Absolute Write Paths — CRITICAL

`delegate_task` subagents get **isolated working directories**. Give every
subagent the **absolute** path to the shared workspace, or they'll write to
their own scratch dir and you'll never find the output. Always pass e.g.
`/mnt/z/pantheon/projects/<p>/tasks/<id>/research/` verbatim in each brief.

## Pre-Flight Dedup (step 0, every agent)

Tell every agent to load the "already-done" inventory BEFORE researching:
existing records (query the live REST endpoint if public), plus any staging
file siblings may have written. Each agent builds an `EXISTING` set and skips
anything already in it (including close-name variants). This is what stops N
parallel agents converging on the same well-known items and wasting cycles.
The orchestrator re-checks at merge for cross-agent duplicates.

## Leaf-agent asset-download checks (logo) — put these in every brief

Raw `curl -sL -o out.png <url>` returns exit 0 even when the server replies
with an error/HTML page or a placeholder. Agents must validate, not assume:

- **Magic-byte check the downloaded file**, never the extension or the HTTP
  code: `head -c 4 x.png | grep -q $'\x89PNG'` (PNG), `GIF` (gif), `<?xml`/`<svg`
  (svg). A 404 page, tiny WebP placeholder, or HTML dump all slip through curl
  silently. Loop over candidate URLs (favicon.ico/png, `/assets/img/logo*`,
  `/logo.svg`, `og:image` content, `apple-touch-icon`) and check each byte
  signature rather than guessing one path.
- **Sanity-check size targets**: reject sub-256px favicon-glyph grabs as
  "quality low"; snap the favicon only when the site exposes no larger official
  logo, and flag it in notes so the curator can source a brand kit.
- **Record which asset proved the brand** (colours/lockup). An `og:image`
  social banner is NOT a logo — prefer the header/brand mark.
- **Re-verify at the end**: in a shared `logos/` dir, a concurrent sibling
  agent or a build step can silently overwrite your file with a different
  (often WebP) asset. Before finalizing the staging JSON, re-check every
  referenced logo is the file you downloaded, not whatever is now on disk.

Provision agents in the same workspace with **distinct slug-scoped filenames**
(`logos/<slug>.<ext>`) so parallel runs can't collide on a generic name.

## Taxonomy expansion / re-tagging

When the goal is adding NEW categories to an existing curated set (not just
growing the old ones), have the leaf agent also emit a **`reassign` block**:
existing `slug`s that belong in the new categories, listed per new category.
That is how the orchestrator/human knows which already-live records to
re-tag — cheap, high-value, and easy for agents to produce since they load the
`EXISTING` set anyway. Leave reassign lists empty for categories that have no
existing members.

## Dispatching (≤ ~5 concurrent)

- Split support ≤ max_concurrent_children (commonly 3); if you have more
  categories than slots, pair small ones together (e.g. two smallest in one
  agent). Never exceed the platform cap.
- **Every brief is self-contained**: absolute workspace path, category + exact
  enum slug, the tool-routing rules, the output contract, the verification
  steps, the quality bar, "no downstream writes" rule.
- Give each subagent the toolsets it needs: `web`, `browser`, `terminal`,
  `file`.

## Monitoring & Driving (the PM part — be ACTIVE, not passive)

- Don't trust self-reports. Check live transcripts and that files actually
  landed on disk.
- If an agent stalls, returns thin/low-quality work, or diverges: re-dispatch,
  tighten its brief, or reassign — keep the team moving.
- **Watch for cross-agent duplicates early** (two agents researching the same
  item) and catch it before merge.
- Environment obstacles (tool missing, site unreachable, SE Ranking down):
  tell the agent to fall back (e.g. plain web search) per the brief and keep
  going.

## Post-Run (do ALL of these before reporting)

1. Merged one structured file (dedupe globally; one record per item; every
   record complete per the field contract; enums valid).
2. Re-run the embedding/index step if the workflow calls for it (e.g.
   `ccc index`) from the project root so new research is searchable — work
   around it if it fails (not a hard blocker).
3. Final quality pass — drop/correct incomplete, duplicate, or invalid
   records. Keep the structured file strictly structured (no free-form chatter;
   that belongs in `.md` notes).
4. Verify the deliverable parses as valid JSON and matches the contract.
5. Report to the user: counts per category, how many assets downloaded, which
   agents needed re-direction, any gaps, and the deliverable paths.

## Non-Negotiables

- You orchestrate; the subagents do the work. You never write the dataset
  entries yourself.
- You never write to the downstream store (DB/CMS). The human ingests.
- Never exceed the concurrency cap.
- Never dispatch an agent without the division-of-labour + tool-routing
  contract in its brief.

## Support Files

- `references/usefulusability-directory-research.md` — worked example of the
  full orchestration shape (category split, staging `tools.json`, dedup, tool
  routing, ccc re-index).
- `references/leaf-agent-logo-and-taxonomy-expansion.md` — leaf-agent recipe:
  header **inline-`<svg>` logo extraction** (the case curl can't reach) plus a
  `currentColor`→concrete-hex fix, name→domain / absorbed-product traps
  (getmarvin→windows company, enjoyhq→UserTesting, abtasty→VWO), magic-byte
  logo validation, favicon "quality low" handling, **re-verify against
  concurrent overwrites AND run a mid-run cross-sibling dedup recheck**,
  unique workspace filenames, and the `reassign` block pattern for adding NEW
  categories to a live curated set.
