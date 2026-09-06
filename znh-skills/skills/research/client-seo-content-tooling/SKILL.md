---
name: client-seo-content-tooling
description: Locate client marimo SEO generators and keyword research.
version: 1.0.0
platforms: [linux]
environments: [hermes]
metadata:
  hermes:
    tags: [seo, thankbox, keyword-research, marimo, content, client, landing-pages, scratch]
---

# Client SEO Content Tooling

Work map for the recurring SEO agencies the user works with (Thankbox is the
primary one). The deliverables fall into two distinct artifact classes that are
EASY to confuse — confirm which class the user means before hunting:

1. **Copy-generator apps** — marimo notebooks that generate on-brand marketing
   copy (titles, descriptions, SEO metadata) for gift-card/theme/category pages.
2. **Keyword-research datasets** — standalone scratch workspaces whose product is
   a CSV + pivot (a landing-page plan), NOT a runnable app.

## Step 1 — Determine the artifact class

Ask/confirm up front whether the user wants a GENERATOR or a RESEARCH DATASET.
This session failed here: user said "theme generator", corrected to "category
copy generator". There are multiple similar-named apps; mis-targeting wastes
turns.

Common generator apps to disambiguate (all exist, all marimo):
- Gift Card **Theme** Copy Generator (image upload → occasion + title/desc)
- Gift Card **Category** Copy Generator (category name → title/desc + SEO meta)
- Gift Card **Country** Copy Generator (country → hero copy + SEO meta, wraps brand names)
- Gift Card **Top Picks** / bulk variants (see references for the full set)

Common research datasets by target:
- christmas card for {recipient} (boss/mom/husband...) — recipient pivot
- bulk christmas cards (business gifting persona, 589-kw cluster)
- gift-card category/country pages

## Step 2 — Find it

Search the PATH the artifact lives in, not the whole repo blindly:
- Scratch workspaces: `scratch/NNN-slug/`
- Pantheon task dirs: `projects/<color>-<beast>/tasks/NNN-slug/`

Effective search: `search_files` for filename stems or a distinctive prompt
string (e.g. `GC_CATEGORY_COPYWRITING_PROMPT`), and grep the
`__marimo__/session/*.py.json` files for the app's markdown title (`<h1>`).
The marimo session dump embeds the rendered header.

## Step 3 — How it runs (server-side vs static/WASM)

Check `pyproject.toml` dependencies to decide accessibility:
- Deps include `google-genai` + `google-cloud-secret-manager` → **server-side**.
  Needs a Python backend + Gemini creds. NOT WASM-able as-is. Run locally:
  `uv run marimo edit main.py` in the scratch dir.
- A `public/` dir containing a bundled `index.html` with `marimo-wasm` →
  **static/WASM build**. Runs in-browser (read mode), no Python needed; API
  calls proxied through a Cloudflare Worker. Can be served over tailnet or
  hosted on Pages.

Tailnet serving: active pantheon tasks use `pantheon serve` (see
`pantheon-serve-static` skill); scratch/out-of-task dirs use the pattern in the
`serving-static-previews` skill. A served app is verified by `serve_url` in
`.task.json` — null means nothing is registered/hosted.

## Step 4 — Summarise research recommendations by group

Research CSV deliverables are grouped by an explicit category (e.g.
`professional` vs `immediate_family`) with per-recipient rows:
- canonical_recipient, total_volume, keyword_count, max_volume, avg_difficulty
- the pivot (per-keyword) vs consolidated (one row per recipient).
Use the **consolidated** CSV for the by-group page table; use the **pivot** for
individual keyword→page mapping. Note the `intents` column (`I`=informational
"what to write", `C`=commercial) — professional clusters skew informational.

## Reference files
- `references/thankbox-artifacts-map.md` — current exact paths + per-artifact
  form (generator vs dataset, server vs WASM) for every Thankbox SEO artifact.
  UPDATE THIS when new scratch/task dirs for Thankbox appear.
