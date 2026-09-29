# Taxonomy Expansion to Many-to-Many Categories — worked example

Worked example: a curated UX/usability directory growing from a fixed 6-category
single-relation taxonomy to a 16-category many-to-many taxonomy while research
was still running. Use as a copy-adapt template for any directory whose owner
wants to add categories and let a tool appear under more than one.

## From / to

**Before (6 categories, `tools.category` is `relation maxSelect: 1`):**
`user-testing`, `prototyping`, `analytics-heatmaps`, `surveys-feedback`,
`accessibility`, `session-recording`.

**After (16 categories, `tools.category` is `relation maxSelect: >1`):**
- Kept/renamed: `user-testing`, `prototyping`, `web-analytics` (renamed from
  `analytics-heatmaps`), `surveys-feedback`, `session-recording`,
  `accessibility`
- New: `product-analytics`, `a-b-testing`, `user-research`
  (User Research & Repositories), `recruiting` (Participant Recruiting &
  Panels), `ui-design`, `design-systems`, `motion` (Motion & Animation),
  `typography`, `colour-palettes` (Colour & Palettes),
  `colour-accessibility` (Colour & Contrast Accessibility)

## Two parallel tracks

1. **Schema/code → OpenCode.** A new migration `000X_multi_category_tools.js`
   (never edit an already-applied migration — follow the `0002_...` evolution
   pattern): flip `tools.category.maxSelect` 1→`>1`, seed the new/renamed
   category records with `name, slug, description, icon, order`, preserve the
   slug-unique indexes and the articles/glossary/tags collections. Frontend
   rework: `Tool.category: string → string[]` in the data layer, and every page/
   component that read a single category becomes array-aware (breadcrumb uses
   the primary/first; sidebar renders "Category" vs plural "Categories" with a
   link per category; the grid filter/search is any-match; related-tools share
   ≥1 category).

2. **New-category discovery → delegate_task research agents (in parallel, NOT
   gated on the schema).** Discovery writes to the staging JSON by slug/category;
   it does not touch the DB, so it can run before the schema is ready. Brief
   agents to skip already-listed tools (they share the 143-slug `tools.json`)
   and, where a tool is genuinely top-in-their-bucket but already listed under
   another category (Figma/Sketch in `prototyping` but belong in `ui-design`;
   VWO in `analytics-heatmaps` but a top `a-b-testing` product; Mixpanel in
   analytics but a `product-analytics` leader; Dovetail in user-testing but a
   `user-research` repository), **skip re-listing it and emit a `belongs-here`
   note** so the re-tag step knows which existing slugs to re-assign.

## Verification after the schema lands

- `ls backend/pb_migrations/` → the `000X_multi_category_tools.js` file exists.
- `git status --short` → new tracked edits in the task frontend.
- Live service — authoritative:
  `curl :PORT/api/collections/categories/records?perPage=200&sort=order`
  → expect exactly the 16 slugs in target order (count + order are the real
  check, not OpenCode's self-report).
- `bun run build` in `frontend/` → no type/build errors, all category pages
  render (46 pages incl. 16 category pages). Spot-check a multi-category tool
  (assign one temporarily, e.g. Maze → `user-testing` + `recruiting`) renders
  both category links and appears under both category routes.

## Re-tag after schema is confirmed ready

Once the live `categories` shows the new count, re-tag existing staged tools
across the new taxonomy (primary + secondary categories) using each agent's
`belongs-here` notes. `analytics-heatmaps` → `web-analytics` is a rename, not a
new bucket — update frontend article-content slug references in the same change
(e.g. `frontend/src/lib/article-content.ts` had 6 refs).

## Pitfall: delegation process lost between turns

A background `opencode run` (background=true, pty=true) can be killed between
user turns — `process poll` returns `not_found`, process list empty, with zero
code landed (the first schema attempt in this session was lost this way). Judge
completion by filesystem + live service, never by a still-registered process;
if the process is gone and no artifact landed, re-dispatch fresh with the same
brief. A migration spanning 9+ frontend files legitimately takes 15+ min across
two attempts — confirm genuinely-progressing via its streaming log (file-edit
diffs), not a guessed duration.
