---
name: thankbox-content-generators
description: "Locate Thankbox content generators and their data on disk."
platforms: [linux]
metadata:
  hermes:
    tags: [thankbox, client, seo, marimo, content, generators, landing-pages]
    related_skills: [tasknotes-board, using-se-ranking-mcp]
---

# Thankbox Content Generators & Data Locations

The Thankbox account has SEVERAL marimo/Gemini apps that generate page copy,
with easily-confused names (theme generator vs category copy generator vs
country copy generator). Locating them from scratch is expensive (~10 tool
calls) — use this map first.

## The generators (where each lives + what it actually does)

1. **Theme Description Generator** (`projects/purple-odin/`, tasks 001→007,
   most advanced at `007-combine-categories/`; production copy in `main/`).
   Uploaded theme **images** + an occasion list → product **title +
   description** for a card theme. Per-variant files: `main.py`, `prompts.py`,
   `llm_logic.py`, `schemas.py`, `config.py`, `znh_secrets.py` (and a WASM
   build in some task `public/`). A "theme" = a card design for an occasion,
   NOT a landing page.
2. **Thankbox Landing Page (LP) copywriter** — a writing PROMPT/SPEC, not a
   runnable tool: `vault/ZNH/AI/Prompts/{Prompt} Thankbox LP copywriter.md`.
   Full page structure (hero H1+intro+CTA, problem/solution, how-it-works,
   why-choose, social proof, final CTA, FAQ) + Thankbox tone. Use this as the
   spec any time the task is to write a full landing page, theme, or
   recipient page.
3. **Gift card category copy generator** (`scratch/004-gc-category-copy/`).
   Generates category page copy (category_title/description, meta_title/
   description) for gift-card categories like "Hotel Gift Cards". Handles
   PRESET_CATEGORIES from `gift_card_categories.csv`.
4. **Gift card country copy generator** (`scratch/005-gc-country-copy/`) —
   for country pages ("Australia Gift Cards"), forked from 004.

Key distinction to avoid mis-naming back to the user: **theme/description
generator** (image→theme blurb), **category copy generator** (gift-card
category page), **country copy generator** (gift-card country page), **LP
copywriter** (full landing-page spec). "Category page" vs "landing page" are
often used interchangeably by the user — ask which pages (schema/occasions)
they mean if ambiguous.

## Keyword-research datasets (scratch)

- `scratch/001-christmas-card-keyword-research/` — RECIPIENT-based Christmas
  landing-page keywords ("christmas card for boss / dad / mum"). Deliverables
  in `data/`: `recommendations_pivot.csv` (every keyword per recipient),
  `recommendations_consolidated.csv` (canonical recipient rollup),
  `recommendations.csv`, `keywords.csv`. Two focus categories: professional
  (boss, coworker, client, manager, business, employee, colleague, customer,
  staff, work, company) and immediate_family (dad, mom, boyfriend, husband,
  wife, grandparent, sister, girlfriend, brother, son, parents, daughter,
  spouse/partner, kids).
- `scratch/009-thankbox-bulk-christmas-cards/` — DIFFERENT, business/bulk
  persona (589-keyword SE Ranking UK cluster). Not the recipient page set.
- `scratch/008-thankbox-gift-cards-optimisation/` — /gift-cards page optimiser
  (Search Console / SEOcrawl + SE Ranking), per-URL KEYWORD_PLAN.md.

## Pitfalls

- Recipient volume is seasonal: annual averages understate Nov–Dec peaks.
  Flag seasonality on any Christmas-keyword card rather than killing words.
- Commercial ("targeted") vs informational ("what to write...") intents occur
  within one recipient cluster; landing page + FAQ/content pages serve
  different rows. Detail lives in `recommendations_pivot.csv` `source_tool`.
- "That would require a dedicated landing page tool" — as of Aug 2026 **no
  dedicated recipient-landing-page generator exists**. Closest is reusing
  `scratch/004-gc-category-copy`'s marimo pattern extended per-recipient +
  the LP-copywriter spec. Route build cards through the tasknotes-board
  handoff (see `tasknotes-board` skill).
