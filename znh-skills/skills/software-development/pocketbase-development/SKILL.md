---
name: pocketbase-development
description: "Evolve PocketBase schemas and wire new fields into Astro."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [pocketbase, schema, migration, backend, astro, sqlite]
---

# PocketBase Development

## When to Use

- Adding, changing, or removing a field/collection in a PocketBase-backed app.
- Wiring a new PocketBase field into a frontend (e.g. Astro) that reads it via
  the REST API.
- Diagnosing "the migration ran but the field isn't there" or a schema/db
  mismatch.

## Non-negotiable: add-only migrations

**Never edit an already-applied migration file** (e.g. `0001_schema.js`). A
field change is a NEW migration (`0002_*.js`) with the established
`migrate((app) => {...}, (app) => {...})` up/down shape. Rationale: PocketBase
replays migrations in order; editing an applied one breaks replay-from-scratch
and silently diverges live DBs. The end state must be: a fresh DB replaying
migrations 0001 → 000N reproduces the final schema with no data dependency.

## Field type for external local assets (logos, images, files)

When a field will hold a **path/URL to an asset that lives outside PocketBase**
(e.g. committed static files under `research/logos/<slug>.<ext>`, served from
`frontend/public/`):

- Use **`text`** for a plain relative path string. It matches how simple
  presentation strings (`card_color`, `initial`) are already stored, and needs
  no constraints.
- Do NOT use `file` — `file` means the asset is a multipart upload stored in
  `pb_data/storage`; an ingest step writing a path string is not an upload.
- Do NOT use `url` — PocketBase `url` fields run URL validation and reject a
  bare relative path like `logos/maze.png`.
- Keep `required: false` for additive fields so existing records (which predate
  the field) are not invalidated; no `system` flag, no max-size/pattern.

## Apply + verify on the live instance

```bash
cd backend && ./pocketbase migrate up
```
- `migrate up` is idempotent and applies only new migrations; a running server
  picks the change up without a restart (verified 2026-08-08).
- **Verify via the API, not just the migration count:**
  `curl -s :PORT/api/collections/<collection>/records?perPage=1` and confirm the
  new field key is present on records (unset text fields return `""`, never
  null/undefined). This is the authoritative proof the field landed.
- `pb_data/` and the `pocketbase` binary stay gitignored; only the migration
  file is committed.
- getSchema-style field-list greps can miss PocketBase's field-list shape —
  trusting the record key is more reliable.

## Wiring the field into an Astro frontend

PocketBase text fields default to `""` (never null), so treat **empty string as
"unset"** and truthiness-test the value.

- Add the field to the `Tool` interface / types in the REST layer (`pb.ts`):
  `logo: string;`.
- In the card/tile component, render `<img src={withBase(tool.logo)} ...>` when
  `tool.logo` is **non-empty**, else fall back to the existing presentation
  block (e.g. `card_color` + `initial`).
- **Always route asset paths through the site's base helper** for subpath-served
  sites (see `serving-static-previews`): a bare `src={tool.logo}` resolve to the
  domain root, not the subpath — use `withBase()`/base-aware URL builder.
- Apply the same empty-check pattern everywhere the field renders (grid card,
  detail page, related-tools tiles, comparison/article tiles).
- Verify BOTH branches: the fallback (real state, all logos empty → original
  markup) AND the image branch (temporarily set a logo on one record, rebuild,
  confirm correct base-prefixed src, then revert the record and rebuild). Leave
  the DB in its true final state.

## Reference

- `references/astro-subpath-and-logo-wiring.md` — worked example from the
  UsefulUsability build: adding a `logo` field, the text-vs-file-vs-url
  decision, live verification, and Astro `withBase()` wiring on a subpath-hosted
  site.
