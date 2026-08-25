# Thankbox SEO Artifact Map

Current exact paths + form for every Thankbox SEO deliverable found under
`/mnt/z/pantheon/`. Verified 2026-08-16. UPDATE THIS when new scratch/task dirs
for Thankbox appear (they accumulate fast — each is `NNN-slug`).

## Copy-generator apps (marimo)

| App | Path | Form | Backend |
|---|---|---|---|
| Gift Card **Theme** Copy Generator | `projects/purple-odin/tasks/002-configurable-occasion-gen/tools/thankbox_generator.py` (source) + `public/pfxwst/index.html` (WASM build) | static/WASM + source | API proxied via Cloudflare Worker `https://tools.znh-dev.com/pfxwst/api/gemini`; `.task.json` shows serve_url/port/pid all null (nothing currently served by pantheon) |
| Gift Card **Category** Copy Generator | `scratch/004-gc-category-copy/main.py` (+ `prompts.py`, `llm_logic.py`, `categories.py`, `gift_card_categories.csv`) | server-side marimo | `google-genai` + `google-cloud-secret-manager` — needs Python backend + Gemini creds, NOT WASM. Run: `uv run marimo edit main.py` |
| Gift Card **Country** Copy Generator | `scratch/005-gc-country-copy/` (fork of 004, same client/tone/LLM) | server-side marimo | same as 004 |
| Gift Card Top Picks (prompt fix note) | `scratch/006-gc-top-picks-prompt-fix/` | handoff JSON inputs | — |

Theme vs Category vs Country are three DISTINCT apps. "Theme" takes image
uploads; "Category"/"Country" take a name and return title/desc + SEO meta.

## Keyword-research datasets

| Target | Path | Product | Notes |
|---|---|---|---|
| christmas card for {recipient} | `scratch/001-christmas-card-keyword-research/data/` | `recommendations_consolidated.csv` (by-group page table) + `recommendations_pivot.csv` (per-keyword) + `keywords.csv` | THIS is the "christmas card for boss/mom/husband..." recipient research. Groups: `professional` and `immediate_family`. Pipeline scripts `fetch/enrich/consolidate/analysis.py` |
| bulk christmas cards (business gifting) | `scratch/009-thankbox-bulk-christmas-cards/` | 589-kw cluster, `RESULTS.md`, `data/keywords.csv`, SERP raw | DIFFERENT dataset — UK exact-match, SE Ranking, business/bulk persona. Has `christmas card for boss` only inside `related_raw.json`; not the recipient-focused plan |
| gift-card category/country pages | `scratch/004-gc-category-copy/gift_card_categories.csv` + `scratch/005-gc-country-copy/` | page naming conventions | referenced by `scratch/008-thankbox-gift-cards-optimisation/008-TASK-BRIEF.md` as the copy generators for those exact pages |

## Distinguishing 001 vs 009

Easy to confuse — both "christmas" keyword research.
- `001` = recipient-personalised plan ("christmas card for X") grouped by
  `professional`/`immediate_family`. Question: which recipient gets a landing page.
- `009` = business/bulk gifting cluster (589 kw) for the bulk-cards persona.
  Question: which bulk/business page to build.

## Consolidated CSV column meaning

From `001`'s `consolidate.py`: one row per canonical recipient, columns
`category, canonical_recipient, merged_from, total_volume, keyword_count,
max_volume, avg_difficulty, regions, intents_present`. `merged_from` lists
spelling variants (e.g. `mom` ← mum+mother+mommy+mummy). `intents_present`
uses `I`=informational ("what to write in a christmas card for..."),
`C`=commercial. Professional clusters skew informational (`I`) with higher
difficulty; immediate_family are lower difficulty (5.5–8) and more commercial.
