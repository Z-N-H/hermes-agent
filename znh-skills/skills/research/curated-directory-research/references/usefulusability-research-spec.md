# UsefulUsability directory — research spec (worked example)

Copy-adapt template written 2026-08-08 for the UsefulUsability UX/usability
tools directory. Useful as a concrete example of a schema-matching staging spec
for any future product/tool directory.

## Schema context (PocketBase, 5 collections)

`categories`, `tags`, `tools`, `articles`, `glossary` + a standard auth/users
collection. Public read; admin-only writes. `tools` list/view filtered to
`status="live"` so the admin UI is the draft-review surface.

`tools` fields: name, slug (unique), tagline, description, overview,
key_features (json array), best_for, website (url), category (relation,
maxSelect 1), pricing (select: free/freemium/paid/free_trial), tags (relation,
max 20), added_at (date), featured (bool) + featured_order (number, composite
index), status (draft/live), sponsored + affiliate_url (monetization room,
unused in v1), card_color + initial (presentation helpers for the image-top
card: solid color block + letter avatar).

## 6 fixed categories (slugs)

`user-testing`, `prototyping`, `analytics-heatmaps`, `surveys-feedback`,
`accessibility`, `session-recording`. One category per tool.

## Pricing enum

`free` (genuinely free at useful scale, e.g. Microsoft Clarity) · `freemium`
(free tier + paid upgrade, most SaaS) · `paid` · `free_trial` (timed trial, no
durable free tier). Pick exactly one.

## Staging JSON shape

```json
{
  "generated_at": "2026-08-08T00:00:00Z",
  "source_note": "…",
  "category_totals": { "user-testing": 0 },
  "tools": [{
    "name": "…", "slug": "…", "category": "user-testing",
    "pricing": "freemium", "tagline": "…", "description": "…",
    "website": "https://…", "logo": "logos/slug.png", "best_for": "…",
    "key_features": ["…"], "tags": ["Unmoderated", "Remote"], "overview": "…"
  }]
}
```

Ingest step resolves category/tags → relations by slug/name, derives slug
uniqueness, assigns card_color/initial. Research agents never touch the DB;
they return this file. Curation then seeds as `status: draft` for admin review.

## Notes that transfer cleanly to other directory projects

- Always dedupe against the **live** collection via the Records API
  (`perPage=200`) before finalizing, not a hardcoded seed list — the live list
  is authoritative.
- Split parallel agents by category (one per 1–2 categories), return per-agent
  JSON, merge then dedupe globally.
- Logo: prefer official brand asset (site `<head>` logo, `/logo.png`,
  `og:image`), SVG > transparent PNG ≥256px, verify decodable, flag low-quality.
- A `logo`/`logo_path` field must be ADDED to the tools schema if you want
  logos rendered on cards — the v1 schema had `card_color`+`initial` instead.
  Collecting logos is decoupled from wiring them into the UI.
