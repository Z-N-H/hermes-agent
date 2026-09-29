# Worked example — UsefulUsability logo field (2026-08-08)

A live case of the `pocketbase-development` patterns, from adding a logo path
to an Astro + PocketBase directory site.

## Task

Research listings each carry a brand/logo asset saved locally (under
`research/logos/<slug>.<ext>`, committed static files). The `tools` collection
needed a field to hold that path, and the Astro frontend needed to render it.

## Schema change

- New file `backend/pb_migrations/0002_add_logo_to_tools.js` — did NOT edit the
  applied `0001_schema.js`. Used the established `migrate((app)=>{...},(app)=>{...})`
  up/down shape.
- Field: `text`, `required: false`, no `system` flag.
- Type decision: `text` not `file` (asset is a path string, not a multipart
  upload to `pb_data/storage`), and not `url` (PocketBase URL validation rejects
  the bare relative path `logos/maze.png`).

## Apply + verify

```bash
cd backend && ./pocketbase migrate up   # "Applied 0002_add_logo_to_tools.js"
```
- Running server picked it up WITHOUT restart.
- Verified via API record (authoritative):
  `curl -s http://127.0.0.1:8090/api/collections/tools/records?perPage=1` →
  records contain `"logo": ""`.
- A naive getSchema-style field-list grep over `/api/collections/tools` did NOT
  surface the field (field-list shape mismatch) — the record key was the
  reliable proof.
- `pb_data/` + `pocketbase` binary gitignored; only the migration committed.

## Astro wiring

- `frontend/src/lib/pb.ts`: added `logo: string;` to the `Tool` interface.
- `frontend/src/components/ToolCard.astro` (and the related-tool tiles on
  `tool/[slug].astro` + `blog/[slug].astro`): render
  `<img src={withBase(tool.logo)} ...>` when `tool.logo` is non-empty, else the
  existing `card_color`-background + `initial`-letter block.
- Empty text field = `""` → used truthiness; `""` falls through to original
  markup.
- `withBase()` required because the site is served under `/usefulusability/`
  subpath; bare `tool.logo` would resolve to the domain root.

## Both-branch verification

- Fallback: built with all logos empty; `dist/` grep showed zero logo refs —
  every current tool renders the color+initial fallback.
- Image branch: momentarily PATCHed Maze to `logo: "logos/maze.png"`, rebuilt,
  confirmed `<img src="/usefulusability/logos/maze.png" alt="Maze logo" ...>`
  on the grid card, related-tool tiles, and the comparison tile — then reverted
  the record to `""` and rebuilt. DB left in true final state.
