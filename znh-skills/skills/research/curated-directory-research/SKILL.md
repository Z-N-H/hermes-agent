---
name: curated-directory-research
description: "Curated product/tool directory research via web subagents."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [research, directory, listings, web-research, curation, staging]
---

# Curated Directory Research

## When to Use

- Building a curated directory / catalogue / listing of products or tools
  (e.g. "best UX testing tools", a tools directory, a marketplace catalogue).
- Ousourcing the discovery + data-collection to web-research subagents.
- Ongoing "listing discovery" passes to grow an existing directory with new,
  vetted entries.

Distinct from `research-toolkit`, which catalogs *research tools* (arXiv, blog
feeds, Polymarket, maps). This skill is the *methodology* for filling a curated
directory with verified entries.

## Core Model: Discovery is NOT a listing

Split research into two phases and keep them separate:

1. **Discovery (broad, creates nothing).** Cast a wide net across many sources:
   web search ("best X tools", "top X"), software directories (G2, GetApp,
   Capterra, Software Advice, Product Hunt), category roundups and comparison
   posts, curated lists, app stores. Compile a candidate list. **Discovery
   alone does NOT qualify a tool.**
2. **Verification (mandatory, per tool).** A candidate only becomes a listing
   after it passes the per-tool workflow below. Discard candidates that fail.

## Mandatory Per-Tool Verification (run for EVERY tool that will be listed)

Do not skip a step; if the tool can't pass, drop it from the dataset.

1. **Find the website URL** — the official product site (not a directory page,
   not an app-store page). This is the `website` field.
2. **Visit the website** — load the homepage, confirm it resolves and is the
   real product (brand/name/offering match).
3. **Browse the site** — navigate the main feature / product / pricing pages.
   Read the actual pages. Never guess from memory or from a directory's
   summary.
4. **Log the required data from what you saw** — using ONLY the browsed pages,
   fill the fields: value prop / description, key features (from feature
   pages), pricing tier (from the pricing page), tags, category. Every claim in
   the listing must trace to something on the site.
5. **Download the tool's logo** — save a copy of the brand/logo (see Logo
   handling below).

If any step fails (site dead, no real product page, no pricing, no logo),
**omit the tool**.

## Delivery: Staging dataset, never DB writes

Research agents return a **staging dataset** (JSON/CSV) that matches the target
schema — **they do NOT write to the database.** A human (or curator) reviews the
dataset, then a seed script ingests it (e.g. as `status: draft` rows for
admin-UI review before going live). Separate concerns:
- Agents discover + verify + log.
- Human curates + approves.
- Seed script ingests.

## Staging schema guidance

- **Match the production schema field-for-field** so the seed step is a
  mechanical resolution, not re-mapping. Relations (category, tags) should be
  emitted as the slug/name they resolve to, and the seed step turns them into
  relations.
- Emit fields that are derived at ingest (avatar initial, card colour, logo
  path) as empty/placeholder strings — the seed assigns them.
- Include a top-level `category_totals` and `generated_at`/`source_note` for
  reviewability.

## Dedup — mandatory PRE-FLIGHT inventory lookup (critical)

Dedup is **step 0**, done ONCE at the start of every agent's run — NOT a
post-discovery cleanup and NOT only "before finalizing slugs". Running it only
at the end wastes research effort and lets parallel agents re-discover the same
well-known tools. For parallel-agent scaling this is the single most important
guard.

- **Before ANY discovery**, each agent loads the authoritative inventory into an
  `EXISTING` set:
  - Query the **live** target collection:
    `GET :PORT/api/collections/<collection>/records?perPage=200` (pull `slug` +
    `name`).
  - If a shared staging file already exists (`<output>/tools-staging.json`),
    ALSO include its entries — they may not be in the DB yet.
  - **ALSO scan sibling `notes/*.md` and the shared `logos/` dir — a sibling may
    have ALREADY done your exact categories but left only notes + downloaded
    logos and NO staging JSON.** A parallel agent that worked the same buckets
    (e.g. agent16 nailed typography/colour-palettes/colour-accessibility and its
    verified logos were already sitting in `research/logos/` — `google-fonts.png`,
    `coolors.svg`, `webaim.png`, `typescale.svg`, …) typically leaves a per-tool
    `name | slug | pricing | logo` table in its `.md`. Before sinking discovery
    effort into a tool, grep the sibling notes + `ls` the logos dir: if a slug you
    were about to research already appears there (even without a JSON entry),
    treat it as covered — do not re-verify, re-log, or re-download its logo.
 This session re-burned the full discovery→verify→logo pass on a
 set agent16 had already completed, because the pre-flight looked only at
 `tools.json` + staged JSON and never at the notes/logos already on disk.
 Reading the newest sibling note early in step 0 is the cheapest dedup gamma.
- Then for the whole run: do not research / list / download a logo for anything
  already in `EXISTING`, including close-name variants (do not add a second
  entry for the same product).
- On overlap **skip immediately and move on** — do not burn discovery or
  verification cycles on it.
- When parallel agents return per-category datasets, **merge then dedupe globally**
  — both against the live data AND against sibling agents' outputs
  (a tool found in two runs is listed once). Each agent runs its own step-0
  lookup; orchestration does the final global merge+dedupe.

### Final cross-agent collision re-check (do this AFTER you write your output)

Because parallel agents write their own files mid-wave, a slug you picked may
have been claimed by a sibling after your step-0 lookup ran. Before declaring
your file done, **re-read ALL sibling per-agent files and `tools.json`** and
re-check your slugs for collisions — not just once at the start. A tool claimed
by a sibling in a *different* category (e.g. Glassbox in `analytics-heatmaps`)
is still a collision: the directory is one row per product, so drop it and
replace it with an equivalent verified candidate rather than double-listing.

Two pitfalls that make this re-check lie to you:

- **Glob self-inclusion:** `glob('agent[0-9].json')` matches YOUR OWN file too,
  so every slug you just wrote shows up as an "existing" collision. Explicitly
  exclude your own file from the EXISTING set (`if a == myfile: continue`)
  before treating the result as a real collision.
- **Name-variant blind spot:** slug comparison catches exact dupes but not a
  sibling using a different slug for the same product. Also do a case-folded
  **name** comparison against sibling `tools` so `"FullStory"` vs
  `"fullstory"` vs a rebrand variant is caught.

## Logo handling

- One logo per listed tool, downloaded from the brand's own site where
  possible (prefer official asset over directory-hosted).
- Save as `logos/<slug>.<ext>`; `logo` field holds the relative path.
- Prefer SVG, else transparent PNG ≥ 256px. Not screenshots, not favicon glyphs.
- Verify the file is a valid, decodable image (non-zero, matches brand) before
  finalizing. Flag "low" quality ones for the curator.
- **A genuinely useful tool with NO usable brand asset is still omittable.**
  Open-source libraries and government/academic tools (e.g. IBM Equal Access,
  SSA's ANDI) often ship only opaque UI screenshots or a small module icon —
  no transparent wordmark, no ≥256px PNG, no official SVG. A UI screenshot is
  NOT a logo (an "ANDI" wordmark buried in a black toolbar render at 3% of the
  frame fails a directory card). Decide per the logo-quality bar, not the
  tool's usefulness: if the only downloadable asset is a screenshot or a
  favicon glyph, omit the tool (and say why in the source_note) rather than
  degraded with a bad image. Exception: an open-source project
  carried under a parent's brand may use the parent brand lockup (e.g. IBM
  Equal Access → official IBM 8-bar blue: same brand, legitimately a "low
  quality slot, curator decides" call — flag it, don't silently ship it).
  **Official small raster is "low quality — ship, flag", NOT "omit".** Free /
  open-source / academic tools that never ship a ≥256px PNG or SVG often expose
  only a small *official* brand raster on their own site (wave-6: NVDA's 200×200
  PNG from nvaccess.org, Color Oracle's 128×128 JPG from colororacle.org).
  An official, decodable, brand-matching small raster from the brand's own host
  is acceptable-low and should be saved + flagged for the curator — do NOT apply
  the ≥256px omit bar to it. Omission is reserved for screenshots, favicon
  glyphs, unrelated/foreign wordmarks. Small-but-official ≠ no usable asset.

### Locating and extracting the logo

1. **Best candidates in order:** the nav/header `<img>`, a `/logo.svg` or
   `/logos/…` path, the `og:image` meta, then `apple-touch-icon.png` (falls back
   to an icon glyph — flag low quality). Check each with `browser_console` /
   `browser_get_images`; many sites expose all of them at once.
   **Distinguish a usable `og:image` from a useless one.** `og:image` is only a
   real logo when it shows a clean brand mark/lockup (e.g. Origami Studio's OG
   card — a white origami crane on a flat blue gradient, no UI chrome). It is
   NOT a logo when it's a product dashboard screenshot or a marketing collage —
   treat that as "no brand asset" (omittable per the bar below), not a win.
   Vision-verify the OG image (`browser_vision`) to tell a brand mark from a
   screenshot before using it as the `logo`; if it's the latter, fall through
   to the presskit/`/brand` page instead.
   for sites whose nav wordmark is just styled text (no `<img>`/`<svg>` resolved,
   e.g. Framer, PostHog at various times), check the **`/brand/` or `/press/`**
   subpage — Framer's `/brand/` (linked as "Brand guidelines"/"Copy logo SVG")
   exposes the official wordmark SVG directly (`framerusercontent.com/images/…svg`).
   **Many brands host branded-asset ZIP packages on a `/presskit`/`/brand`
   subpage** (e.g. Justinmind's `presskit/` → `horizontal-logo-color.zip` hosted on
   its own S3 bucket). When a homepage shows only an inline/white SVG, open the
   reachable press page from the footer ("Brand assets"/"Press Kit") and `curl`
   the named logo zip, then `unzip -q` it and use the extracted PNG/SVG — that
   gets you the true multi-colour horizontal lockup, not the recoloured guess.
   Probe candidate SVGs from the brand page with `browser_navigate`+`browser_vision`
   before saving; pick the one that renders the real lockup, not a blank-white
   or a different product's mark.
   for the walk (/brand flag lens) — see `references/logo-acquisition-wave6.md`
   for the three new channels landed this wave:
   - **Cookie-consent-CDN logos (OneTrust/cookielaw.org).** Many brands' cookie
     banner is hosted by a consent vendor that also stores an OFFICIAL brand PNG.
     When the homepage only yields an inline/white SVG, query the DOM for
     `img[alt="<Brand> Logo"]` — Heap's `heap-logo.png` (500×197) surfaced from
     `cdn.cookielaw.org/logos/...` this way. Official, decodable, brand-right;
     a legitimate grab before the screenshot/favicon fallbacks.
   - **Strip the Next.js `/_next/image` optimizer and curl the underlying CDN
     asset directly.** Pendo's nav logo resolved as
     `pendo.io/_next/image/?url=<enc)%2Fbuilder.io…%2F<asset-id>>&w=384` — the
     real file is the decoded `cdn.builder.io/api/v1/image/assets/...` URL.
     `curl` that CDN URL directly (no proxy), and do NOT trust the filename:
     builder.io returned `pendo.svg` even though the fetch was named `.png`.
   - **Very large inline nav SVGs → extract from fetched HTML source, don't
     hand-copy.** Woopra's whole nav lockup is one ~12KB inline `<svg class="logo"
     viewBox="54 0 507 242">`. Instead of pasting that string, `curl` the page
     HTML and regex out `r'<svg[^>]*class="logo"[^>]*>.*?</svg>'`, then write it
     with `write_file`. (Keep using `write_file`, never a terminal `python3
     heredoc`, for this.)
   - Also note the **Cloudflare CAPTCHA caveat** documented in
     `references/logo-acquisition-wave6.md`: a clickable "Verify you are human"
     checkbox may be clicked yet still never resolve in a no-proxy headless
     browser — timebox it, then fall through to omit / partner-merge.
2. **Direct-file download:** once you have the URL, `curl -sL -o logos/<slug>.<ext> "<url>"`
   (add a `-A "Mozilla/5.0"` UA — several sites 403 a bare curl). Save via
   curl/`file` write, do NOT pipe a favicon/og:image through a text tool.
   **Content-negotiation gotcha:** a `?format=png` URL can still return webp if
   your curl `Accept` echoed `image/webp` — force `-H "Accept: image/png"` and
   re-check the magic number, don't trust the URL. And "HTTP 200 but
   `text/html` SPA" for a logo asset usually means the CDN wants browser-like
   image `Accept`+`Referer` headers, not that the asset is missing (see
   `references/logo-acquisition-wave4.md`).
3. **`browser_get_images` blind spot (important):** homepage image lists routinely
   OMIT the nav logo — Stark, Fullstory and LiveSession all inline their
   wordmark as an inline `<svg>` in the header that `browser_get_images` never
   returns. If the logo is missing from the image list, query the DOM for it
   (`document.querySelector('nav a img')`, `'svg[aria-label="<Brand> Logo"]'`,
   or search `footer`/`.brand-logo svg`), and pull `outerHTML`.
4. **Inline `<svg>` → file:** capture the full `outerHTML` via `browser_console`,
   then write it with `write_file` as a complete, self-contained SVG (add the
   `<?xml…?>` + `<svg …>` wrapper and root it at a clean `viewBox`). **Do not
   hand-truncate long path data** — a single garbled `d` attribute destroys the
   logo. If the mark comes out single-colour/`currentColor`, give it the brand
   hex on the `<path fill="…">` so it renders without context. CV: never write
   this via a terminal python heredoc — users block file-writes done through
   `python3 - <<'PY'`; use `write_file` for authored/transcribed content and
   `curl -o` for verbatim downloads.
5. **White / dark-mode-only logos are a real trap.** Header `<svg>`s pulled from
   dark-themed sites are frequently `fill="#fff"` white (Rive's site, VWO's dark
   variant). Saved verbatim they render empty — the wordmark is invisible against
   a white directory card. When `browser_vision` (open the saved file via
   `file:///…` + screenshot) shows a blank/white canvas, the asset is a light-on-dark
   variant: rewrite the fill to a dark brand hex (`#2F2F4A`-style) OR fetch the
   dark-on-light variant from the presskit/`/brand` page. Always vision-verify the
   *saved file specifically with the transparency/padding you intend to ship* —
   an SVG that renders on the vendor's dark nav can be invisible on your light card.
6. **Verify after every save:** `head -c` should show `<svg …>`, and the size
   must be non-trivial (a 600-byte "logo" is usually an error page or a stub).
   `file`/`xxd`/`identify` may be absent from the host — validate PNGs via the
   `89504e470d0a1a0a` magic / `struct` dimensions and SVGs via well-formed tags.
6. **Advanced inline-SVG cases:** header logos are often inline `<svg>`s that
   don't survive a naive save — `<use href="#symbol">` defs, Tailwind
   `fill-accent-*` classes (resolve the oklch colour and inline a hex), groups
   that render off-canvas until a CSS transform is restored, and base64
   base64 data-URI logos. See `references/inline-svg-logo-techniques.md` for the JS
   probes, the oklch→sRGB converter, and the bot-protected-homepage fallback
   chain (try curl w/ full UA → app/login/accounts subdomain → omit the tool if
   if no official logo; never substitute a third-party favicon glyph).
   - **For a very large inline nav SVG where curl of the page HTML fails (JS-rendered
     site) AND hand-copying is unreliable, transfer it out via a base64 `window`
     variable.** A big header wordmark (Zeroheight's is ~9.7KB of `path@d`) is too
     long to paste safely. Instead: in `browser_console`, serialize the `<svg>` and
     base64 it into a global — `(()=>{const s=new XMLSerializer().serializeToString(
     document.querySelector('a[aria-label*="homepage" i], header a, a[href="/"] svg'));
     window.__z=btoa(unescape(encodeURIComponent(s.replace('fill="currentColor"',
     'fill="#111111"'))));return window.__z.length})()` — then read `window.__z` back
     (one ~13KB console return), and decode it to a file with `base64.b64decode()` +
     `write_file`, recolouring `currentColor`→dark ink. Quiz: recolour BEFORE encoding
     so the shipped SVG is self-contained. This keeps every path byte-exact.
   - **A header brand that's a `<use href="#symbol">` is EMPTY — extract the `<symbol>`
     DEF, not the Use, and inline it as a standalone `<svg viewBox=…>`.** Cavalry's
     lockup rendered as `<svg viewBox="0 0 141 54"><use href="#cavalry-logo"/></svg>`;
     `document.querySelector('symbol[id*="cavalry"]').outerHTML` holds the real paths
     (watch for `fill="currentColor"` and `<clipPath>`/`<defs>` you must keep). Serialize
     that symbol and write it root the same way as the base64 method.
   - **A wordmark can be spread across MULTIPLE sibling inline `<svg>`s, all
     sharing one `viewBox`.** GSAP's header brand (wave-8) is three separate
     `<svg viewBox="0 0 82 30">` elements, one per letter/group, each carrying
     `<path d>`s for its portion. `document.querySelector('[aria-label] img')`
     and single-SVG probes miss them. Enumerate ALL of them before choosing:
     `Array.from(document.querySelectorAll('header nav svg, header svg')).filter(s=>s.querySelector('title') && s.querySelector('title').textContent==='<BRAND>')`
     then collect every `path@d`. Merge them into ONE self-contained file with
     a single header `<svg viewBox="0 0 82 30">` containing all the paths —
     don't save three fragments or the letters never form the wordmark.
   - **When a brand's wordmark is `fill="currentColor"` (not white), resolve the
     ACTUAL ink before writing.** Probe the computed colour of the anchor that
     owns the SVG (`getComputedStyle(document.querySelector('a[href="/"], header a')).color`
     → often a near-black like `oklch(0.145 …)`/`#1A1A1A`) and rewrite the path
     `fill` to that dark hex so it renders on a light card. Vision-verify the
     saved file, not just the live DOM. Zeroheight, Motion, GSAP all hit this.
   - **If a logo `curl` download is USER-DENIED (blocked security prompt), fetch
     the SVG text same-origin from inside the page instead** — the identical
     pivot already used for WAF-403s:
     `(async()=>(await fetch('<same-origin logo url>',{credentials:'omit'})).text())()`
     in `browser_console`, then `write_file` the returned SVG text verbatim
     (Backlight's `bkl.svg.svg`, wave-8). Don't retry the denied curl, don't
     substitute a favicon glyph — the in-page fetch yields the official asset.
7. **Wave-3 acquisition ladder for the no-SVG-anywhere case** (JS-heavy terms,
   image-CDN brands, CSS-drawn marks):
   - **Next.js / asset-CDN sites:** logos live at hashed paths like
     `/images/logos/<brand>-logo.svg` or Next `/&#95;next/static/media/<brand>-logo.<hash>.svg`
     (AudioEye). Enumerate what actually loaded — don't guess the hash string:
     `document.querySelectorAll('img[src*="logo"], source[srcset*="<brand>-logo"]')`
     in `browser_console`, then strip the cache-buster query (`?dpl=…`) before curling.
   - **WAF that 403s curl even with a full UA:** AudioEye returned an HTML page
     to a browser-UA curl. Fetch the SVG **same-origin from inside the page**
     instead: `(async()=>(await fetch('<same-origin logo url>',{credentials:'omit'})).text())()`
     in `browser_console`, then `write_file` the returned SVG text.
   - **CSS-drawn / text-only wordmark (no image asset):** GoAccess's "logo" is a
     pure-CSS 3D cube + styled text, and Wireframe.cc's brand is inline
     text/glyphs — there is NO file to download. Fall to a Mark-only brand:
     `document.querySelectorAll('svg[viewBox]')` near the header to capture an
     inline mark.
   - **Project logo lives in the GitHub repo, not the site:** when the homepage
     offers no asset, walk the repo tree via
     `api.github.com/repos/<org>/<repo>/git/trees/master?recursive=1`, filter
     paths for `logo|images|svg|png|ico`, and pull e.g.
     `raw.githubusercontent.com/<org>/<repo>/master/resources/<name>.svg`
     (GoAccess → `resources/goaccess.svg`; Pirsch → root `logo.svg`). Two repo
     locations worth probing that are easy to miss:
     - **`<root>/public/favicon.svg` is often a FULL-SIZE brand lockup, not a
       browser glyph.** JS-SPA products (Excalidraw, wave-5) keep their only
       clean mark there — `raw.githubusercontent.com/<org>/<repo>/master/public/favicon.svg`
       was a 1000×1000 white rounded-square lockup. Don't skip `favicon.svg`
       inside a repo tree because the word says "favicon".
     - **`web/public/logo512.png` / `logo192.png`** (= `assets/logo512.png`):
       Next.js/static frontends ship a 512×512 transparent mark there
       (Swetrix, wave-5) — a genuinely ≥256px asset, not a glyph.
   - **Probe file-extension variants of a product-site logo path.** PHP/static
     hosts expose brand assets under a stable dir (DubBot → `_image/`) where the
     HTML `<img>` points at a `.jpg` but the SAME stem serves an official SVG
     (`_image/dubbot-primary-logo.svg`, 304×74 wordmark, and a secondary SVG).
     Try the `.svg` (and `-logo.svg`/`-secondary-logo.svg`) for a stem before
     settling for the raster. Similarly, recover an SPA header's inline mark SVG
     (e.g. Swetrix's 5-dot gradient mark) exactly as a standalone SVG.
   - **`favicon.ico` can embed a full-size PNG — extract it rather than writing
     it off as a "small glyph".** Products that ship only a `favicon.ico` (Ackee,
     wave-5: `dist/favicon.ico`, 53KB) frequently embed a 256×256 PNG of the real
     brand mark inside the ICO container. Parse the ICO, locate the embedded
     `\x89PNG`, splice its bytes (`png_start` .. `IEND`+4), write it as `<slug>.png`,
     and confirm the dims ≥256 via `struct.unpack('>II', png[16:24])`. A clean
     extracted mark meets the bar and avoids an omit.
   - **Mark-only vs lockup:** a repo/site may expose only the small geometric
     mark (Pirsch's 277-byte `logo.svg`), not the full wordmark — usable but
     low-detail; flag it for the curator, don't ship it silently.
   - **No asset at any depth ⇒ omit.** Principle (Mac app, wordmark only) and
     Wireframe.cc (text/glyph brand) had no clean downloadable logo and were
     legitimately omitted despite being eligible tools. Record the omission in
     `source_note`.
   - **The marketing-site `<svg>`/wordmark you extract can be the WRONG SKU or a
     parent/campaign lockup, not the product you're listing.** Wave-5: on
     `yandex.ru/adv/metrika` the header `<svg data-testid="Logotype">` rendered
     the generic Yandex **"Реклама"** (advertising) wordmark in white, not the
     **Yandex.Metrica** product lockup — capturing it would have shipped the wrong
     brand. Before you bake a header logotype into the listing, vision-verify the
     **logotype TEXT matches the product name** (`browser_vision`, zoom the corner),
     not just that an SVG resolved. If the only reachable mark is a different
     product's or a parent's, treat the tool as having no usable official logo
     and omit it (flagging RU/geopolitical considerations separately for the
     curator) — same drop-if-no-brand-asset discipline as the white/`currentColor`
     trap.

See `references/logo-extraction-and-defunct-detection.md` for the worked
cross-site examples (extraction snippets per pattern + the small-SVG, add-fill
fix); the wave-3 variants (Next.js hierarchy, WAF same-origin fetch, GitHub-repo
logo fallback, mark-only) are captured in `references/logo-acquisition-wave3.md`;
; wave-4 additions (content-negotiation `Accept` gotchas, Simple Icons
monochrome-mark fallback for bot-blocked/white-only brands, cross-site
dead-competitor detection via rival migration banners) are in
`references/logo-acquisition-wave4.md`. Wave-5 additions (`favicon.ico` embedded
full-size PNG extraction, GitHub `public/favicon.svg` & `web/public/logo512.png`
classics, the `_image/` `.svg`-variant probe, parked-domain defunct detection,
and web-backend-rules-can-lie DNS confirmation) are in
`references/logo-acquisition-wave5.md`. Wave-6 additions (cookie-consent-CDN
`cdn.cookielaw.org` logos, stripping the Next.js `/_next/image` optimizer to
curl the CDN asset direct, regex-extracting very large inline nav SVGs from page
HTML, and the Cloudflare "Verify you are human" CAPTCHA-click-caveat) are in
`references/logo-acquisition-wave6.md`.

## Running the research subagents (execution vehicle)

- **Terminal access is mandatory** on any subagent that must download logos —
  saving a binary image needs `curl`/a file write, not just web text extraction.
  When dispatching via `delegate_task`, grant the `terminal` (and `file`) toolsets,
  not just `web`. Text-only agents can discover + log data but cannot land the
  logo asset, so split that capability accordingly.
- **Subagents have isolated working dirs** — they share no session CWD. Give
  every agent the **absolute** output path (e.g.
  `/abs/path/tasks/<id>/research/<category>.json` and the matching `.../logos/`)
  in the brief; do not rely on relative `research/` resolution. Create the
  output dir (`research/` + `research/logos/`) before dispatch.
- **Brief must be self-contained.** Subagents have no memory of the parent
  conversation: inline the full workflow (discovery→verification→logo→merge),
  the fixed category/pricing enums, the `EXISTING` dedup set source, and the
  deliverable path. Pointing at a spec file the subagent can read is fine if it
  can reach it; otherwise paste the essentials inline.
- **Each agent writes its OWN output file — never let parallel agents append
  to a shared staging file.** Concurrent writes to one shared
  `tools.json`/`tools-staging.json` clobber each other (read-modify-write race)
  and corrupt the deliverable. Give every agent a distinct absolute output path
  (e.g. `research/agent1.json`, `research/agent2.json`, …) whose per-file shape
  matches the staging schema; the orchestrator does the global merge + dedupe
  from those into the single canonical deliverable after ALL agents land.
  Parallel agents are effectively racing separate files, so the merge is the
  only serialized step. During merge, assign a primary category to any tool
  that legitimately spans categories, and flag cross-category duplicates for
  the curator rather than silently dropping them.
- **Parallelize by splitting the fixed categories** across agents (one agent
  per 1–2 categories) up to the delegation concurrency limit, each running its
  own step-0 dedup, then orchestrate the global merge+dedupe at the end.

### Reconstructing a cut-off agent's deliverable from its transcript

A parallel agent can be killed / time out / exit-0 mid-way, having verified tools
and downloaded logos but **never written its staging JSON** (recovery shortfall:
`final` status=completed with `summary: "…let me now write the JSON"` but no file).
When you are re-dispatched to fill that hole, you do NOT repeat the whole
discovery→verify→logo pass. Recover it from the delegation transcript, then
re-verify cheaply:

1. **Read the live transcript first.** `delegation/live/<delegation_id>/task-<n>.log`
   is append-only and streams every child `think`/`tool`/`result`. It tells you
   EXACTLY which tools were chosen, which verified (reachability 200s, pricing,
   features), which were rejected/dead (parked domains, no-logo omissions), and
   which logos were downloaded. Purpose it BEFORE touching any site — it is the
   cheapest ground truth on the recovered file.
2. **`ls` the shared `logos/` dir** — this is the honest progress signal of what
   the prior agent actually landed and its exact filenames (`fontsource.svg`,
   `paletton.png`, …). Your `logo` field must match the on-disk filename exactly.
   For the ONE genuinely-missing logo an already-chosen tool needs, grab it via
   the in-page fetch → `write_file` pivot (see Logo handling), not a broad batch
   `curl`.
3. **Re-derive the dedup set programmatically, not from memory.** Parse
   `tools.json` (the `meta.existing_tools` list AND every `tools[].slug`) plus
   ALL sibling per-agent staging files in one `python3 -c "…"` sweep and diff
   against the slugs you're about to emit. This session's recovered set collided
   with NOTHING, but the sweep is what proves it — a tool that's already listed
   (e.g. `coolors`, `adobe-color`, `fontjoy`) must be dropped or re-tagged, never
   re-listed.
4. **Re-verify from the LIVE site, don't trust the transcript alone.** The
   transcript's reachability list is a good filter, but refresh each candidate's
   tagline/description/pricing from a live `web_extract`/browser pull before
   writing it — sites drift and the recovered fields must trace to the current
   page. Keep the recovered field COUNT/set; refresh the wording.
5. **Emit a `reassign`/re-tag note alongside the new listings** when the
   recovered categories overlap already-listed inventory (e.g. colour-accessibility
   collides with the existing `accessibility` bucket → list the existing slugs to
   re-tag in your notes, don't relist them).
6. **Final validation sweep** (field bar + cross-agent collision + logo→file
   resolution) before declaring done — same as any wave, using
   `scripts/validate-staging.py` or the equivalent programmatic check.

Two tooling gotchas hit while reconstructing:

- **`execute_code`'s `read_file` returns LINE-NUMBERED content** (`1|…`, `2|…`),
  so `json.loads(read_file(path))` fails with `JSONDecodeError: Extra data`.
  To parse a JSON artifact, read it with `terminal python3 -c "import json,…"`
  against the real path, OR strip the leading line-number prefixes before
  `json.loads`. Don't burn a failing round-trip on the line-numbered variant.
- **Broad `terminal` commands can be user/security-DENIED mid-run** — a
  multi-site `curl -o` logo batch and even a `python3 - <<'EOF'` validation
  heredoc were both refused, while narrow single-purpose `python3 -c "…"` reads
  succeeded. Keep network-download and file-write operations narrow and per-item
  (or use the in-page SVG fetch → `write_file` for logos), and prefer single-line
  `python3 -c "…"` over heredocs for validation. See
  `references/reconstructing-cutoff-deliverable.md` for the worked newcat3 example
  (which tools came back, how the dedup sweep was run, the re-verify path).

## Monitoring & driving — be ACTIVE, never idle-wait

The default posture of a background `delegate_task` batch is **passive** and
it is wrong: the consolidated result only re-enters the conversation when ALL
subagents have finished, so if you simply sit and await that notification you
are blind to stalls and blocking for the entire run. The user has explicitly
called this out ("you don't seem to be monitoring them or working agentically").
Do not wait for the batch — drive it:

- **Poll the live transcripts on a cadence** (`tail -f` / repeated `tail` of
  each `delegation/live/<delegation_id>/task-<n>.log`), not just at the end.
  Each child streams its `think`/`tool`/`result`/`final` lines there in
  real-time.
- **Watch for stalls and blocked commands.** A common stall: a subagent's
  `terminal` call is **denied by the security/approval layer** (e.g. a
  big inline `python3 - <<'PY'` base64-write). The blocking message tells the
  agent to stop and wait for a human — which, in a headless research run, can
  hang it. Check the transcript to confirm it self-recovered (a well-briefed
  agent pivots, e.g. from the denied heredoc to extracting the SVG via
  `browser_console` instead). If it hasn't, re-brief or re-dispatch that agent.
- **You cannot inject a new instruction into an already-running remote
  subagent** — it only returns one final summary. If a correction would apply
  to work already in flight, weigh re-dispatching (throw away the stuck
  agent's progress) against letting it finish and fixing at merge. For a
  rejected-weapons-style mid-run change (e.g. "use playwright to download the
  icon, don't recolour in the shell"), first CHECK whether the agent already
  settled on the right approach on its own before deciding it needs help.
- **Track real output, not self-reports.** `ls` the `research/logos/` dir and
  the per-agent JSON/`.md` files while they run — file growth is the honest
  progress signal. Agents typically save logos first and emit their structured
  JSON last, so empty JSON early is normal, not a stall.

## Multi-wave iterative research (recursive listing growth)

Directory research is rarely a single pass. For an ongoing/continuous listing
task, run **successive waves** of subagents until diminishing returns, not a
one-shot dispatch. This is how the user wants continuous listing discovery to
behave — do NOT stop after one wave and hand over a partial set.

**Protocol:**

1. **Wave 1:** dispatch your parallel category-agents as usual (per "Running
   the research subagents"). Each per-agent output file lands, orchestrator
   merge + global dedup.
2. **Merge each wave into ONE canonical staging file** (e.g. `research/tools.json`
   with a `meta.existing_tools` list + `tools` array) against BOTH the live
   backend collection AND the already-accumulated entries. One tool per slug;
   flag (don't silently drop) legitimate cross-category spans. Keep `tools.json`
   strictly structured.
3. **Re-dispatch the NEXT wave immediately** — do not idle between waves — with
   the FULL accumulated inventory baked into every agent's brief as the
   `EXISTING` skip-list, and each agent told to re-read the canonical staging
   file + hit the live backend as its pre-flight (step 0). 
4. **"Go deeper" instruction.** After the first wave the obvious top-tier names
   in each category are gone. Explicitly tell later-wave agents the covered set
   and to focus discovery on LONG-TAIL / niche / newer-entrant /
   developer-leaning / open-source / self-hosted / privacy-focused / vertical
   products and competitor alternatives — i.e. `research/tools.json` is your
   dedup baseline, and "curated but less obvious" is the target. Quality bar
   stays the same (verified, no hallucination, no dupes).
   **Rising bar at depth:** once the catalog is large, switch the brief from
   "fill quotas" to "prefer FEWER excellent NEW tools" — and say explicitly
   that returning **zero** is acceptable when every legitimate option in a
   category is already covered. An agent that pads with marginal tools to hit
   a number is worse than one that returns nothing.

   **Later-wave briefs must carry TWO skip components, not one:** (a) the
   `EXISTING` list of already-listed tools, AND (b) a **`KNOWN-BAD` list** of
   tools vetted-defunct / blocked in EARLIER waves (Smartlook EoS, Delighted
   shutdown, UserZoom→UserTesting merge, Tenon shutdown, dead DNS like
   dora.run, 403-wall like Alchemer). Each wave's agents will surface new
   rejects; fold them back into the KNOWN-BAD list so no future wave re-burns
   research cycles re-discovering that Smartlook/Tenon/etc are dead. This is
   as important as the EXISTING dedup baseline — verified-reject knowledge is
   durable and compound.
5. **Run agentically once approved.** After the user green-lights the loop, do
   NOT pause to ask permission before each wave. Fire the next wave, announce
   it, and keep going.

   **Pitfall — an APPROVED dispatch that only lives in a TODO is not a
   dispatch; fire it in the approval turn.** When multiple tracks are running
   (e.g. a schema/refactor handed to OpenCode AND an approved new-category
   research wave), do not queue the research dispatch to a TODO while you
   "stay responsive" on the code track. A dispatch is not done because you
   planned it and it's on your list — it is done when the subagents are
   actually running. This session the research was approved ("yes launch
   discovery in parallel now") but only parked in todos while the schema
   change got prioritized, and minutes later the user asked "we launched a
   second wave... where are they now?" — the honest answer was that the
   research had never been dispatched. If a dispatch was approved and you did
   not fire it, say so plainly and run it immediately rather than implying
   it is in flight or has made progress. Also re-check the agent-count/commit
   and the left-over process state before reporting a wave is "running" —
   a `delegate_task` batch that was dispatched but never committed to a
   delegation_id leaves no live-transcript dir and no progress to poll.
   If you cannot find the delegation's live transcripts on disk, the wave was
   never launched and nothing is making progress.
6. **ANNOUNCE every dispatch.** Before each wave say: which agents, which
   categories, the EXISTING dedup baseline count, AND the running wave counter
   (e.g. "WAVES RUN: 4 of 10, wave 5 dispatching") so the remaining cap is
   always visible alongside the announcement. Then confirm when the wave lands
   with the merge delta (e.g. "+25 new, 130 in tools.json + 10 DB = 140"). The
   user wants visibility into each dispatch even when they've already approved
   the loop — keep each announcement compact and factual.
7. **Termination.** Stop re-dispatching when a wave returns few/no genuinely-new
   unique tools (diminishing returns) OR when a hard wave-cap is reached (e.g.
   user says "maximum of 10 waves"). Never exceed an explicit cap.

**Late-wave (wave 6+) operation:** once categories approach ~20+ entries, run a
*depletion sweep*, not an equal rotation. Quantify per-category totals first,
budget effort by deficit (the 1–2 thinnest categories are where finds remain),
admit **0 for saturated categories** and say so explicitly (a padding entry is
worse than an honest zero), and write a per-category saturation statement so the
next wave knows what's left and what not to re-research. Gap-filling at depth
often comes from established **open-source / academic / community-standard FREE
tools** (Color Oracle color simulator, NVDA screen reader) that fit the `free`
enum and were never in SaaS roundups — not only newer startups. Full protocol
and worked example in `references/late-wave-saturation-sweep.md`.

Also verify agents that hit a denied/blocked command (see Monitoring & driving)
recovered on their own before assuming a wave failed; a wave is "landed" only
once its per-agent output files are actually written, verified against
`tools.json` for zero slug collisions.

## Taxonomy expansion: adding categories + the many-to-many switch

Directories don't stay fixed at their seed categories. When the owner decides to
grow the taxonomy (e.g. a 6-category usability directory adding colour,
typography, motion, A/B testing, design-systems, product-analytics) you usually
also need to switch the data model from **one-category-per-tool** to
**many-to-many** (PocketBase `category` relation `maxSelect: 1` → `>1`). Two
tracks must be coordinated — run them in PARALLEL, not serially:

1. **Code/schema track → delegate to OpenCode** (it's a coding task, not
   research): a new migration (`000X_multi_category_tools.js`) that flips
   `maxSelect` to `>1`, seeds the new category records (slug, name, description,
   icon, order), and a frontend rework of the `Tool` data type (`category:
   string → string[]`) plus every page/component that reads a single category.
   Verify AFTER it lands by reading the LIVE backend's `categories` collection
   and confirming the count + order matches the target taxonomy, then confirm
   Then confirm the frontend build passes and a multi-category tool renders both categories.
      **Check on-disk + live-service artifacts, NEVER the process table.** A
      background `opencode run` can be lost between turns (session_id `poll` →
      `not_found`, process list empty) with **zero code landed** — so "is it done?
      why is it slow?" must be answered by `ls backend/pb_migrations/`, `git
      status --short`, and `curl :PORT/api/collections/categories/...`, not by a
      vanished process entry. If the process is gone AND no migration/diff landed,
      re-dispatch fresh with the same brief; don't report progress on a dead run.
      A migration spanning 9+ frontend files legitimately takes 15+ min across two
      attempts — confirm from its streaming log (real file-edit diffs) that it is
      genuinely working before calling it slow.
      **Exit code 0 is NOT proof the work is complete.** The tracked background
      `opencode run` can report "completed normally (exit code 0)" while only a
      PART of the change landed — e.g. it wrote the new migration and 5 of 9
      frontend files, but skipped the seed-script reconciliation and never ran
      the build. Worse, nothing stops a *continuation* process (same command,
      same workdir, started later, no tracked session_id) from having picked up
      where the reported-done run left off and still being alive. After any
      schema/refactor delegation, verify the FULL requirement set against disk +
      live service (`ls` migrations, `git status --short` for the frontend diff,
      `curl :PORT/...` for the live category count), and check for lingering
      `ps aux | grep "opencode run"` processes before concluding. Report
      `exit-0-but-partial` honestly and re-dispatch for the remainder when the
      on-disk diff is incomplete — do not trust the exit code or the
      notify_on_complete message alone.

   See `references/taxonomy-expansion-multi-category.md` for the worked 6→16
   many-to-many example: the exact target taxonomy, the two parallel tracks
   (OpenCode schema change + un-gated research dispatch), the `belongs-here`
   re-tag signal, the live-backend verification commands, and the lost-background-
   process pitfall.
2. **Research track → dispatch new-category discovery NOW, un-gated on the
   schema.** The discovery writes to the staging JSON by `slug`/`category` —
   it does NOT touch the DB and does NOT need the schema to be ready. Running
   it in parallel means the research isn't idle while OpenCode churns on the
   migration. The new tools simply sit tagged in staging until the schema is
   ready to receive them.

**"Belongs-here" flag pattern.** New-category agents will collide with the
already-listed inventory (e.g. `figma`/`sketch` already sit in `prototyping`
but belong in the new `ui-design` bucket; `vwo` in `analytics-heatmaps` but is
a top `a-b-testing` product). Brief new-category agents to handle this
explicitly: if a tool is genuinely top-in-THEIR-bucket but already listed under
another category, **SKIP re-listing it** (it's already in the dataset) and emit
it in a `belongs-here` note in their summary, so the re-tag step knows which
existing slugs to re-assign. Their NEW listings must be tools not yet in the
dataset at all.

**Concrete `reassign` output convention (wave-8 example).** Instead of a loose
"belongs-here note in the summary", have each new-category agent emit a
top-level `reassign` dict in its own staging JSON: `{ "<category-slug>":
["existing-tool-slug", …] }` listing every EXISTING slug (from tools.json +
DB pre-flight) that genuinely belongs in the agent's new bucket. Rules that make
this merge cleanly:
- **A cross-bucket tool appears in MULTIPLE reassign lists** (e.g. `spline`,
  `figma` land in both `ui-design` and `design-systems`/`motion`) — that's
  expected and correct under many-to-many; don't dedupe it out. Flag in the
  notes that the seed/curator must pick the primary category and set the rest
  as secondaries.
- Reassign lists are EXISTING slugs only — never include the agent's OWN new
  listings there (those carry their `category` field already).
- Also emit the reverse signal in `source_note`/notes when a well-known tool
  was deliberately NOT re-listed because it was already in another bucket
  (e.g. Swimlane/Lyssna-style rebrand skips), so the orchestrator knows the
  candidate was considered and rejected rather than forgotten.

**Re-tag after the schema lands.** Once the migration is applied, re-tag the
existing tools across the new taxonomy (assign each tool to its primary + any
secondary categories). This step is unblocked only by the schema being ready
(many-to-many must exist to accept an array), so sequence it AFTER confirming
the live `categories` count, not before. `analytics-heatmaps` → `web-analytics`
is typically a rename, not just a new bucket — the frontend/article-content
references to the old slug need updating in the same change (see
`frontend/src/lib/article-content.ts` occurrences).

**Merge mechanics once tools carry `categories[]`.** When the staging JSON gives
each tool a primary `category` AND a `categories` array (for many-to-many), the
merge must reconcile BOTH fields, not just one:
- **A persisted staging file that predates the many-to-many switch has a single
  `category` field; the new taxonomy expects an array.** During merge, initialize
  `categories` = `[category]` for legacy rows, then append each re-tagged bucket
  from the agents' `reassign` dicts. Run the merge idempotently — re-reading the
  staging file and re-applying the rename/reassign should yield the same output.
- **Rename reconciliation across a rename (e.g. `analytics-heatmaps` →
  `web-analytics`):** replace the old slug in BOTH `tool.category` AND every
  entry of `tool.categories` (or the legacy analytics tools keep pointing at a
  slug that no longer exists in the DB). A `grep -c '\"analytics-heatmaps\"'` on
  the staging file after the merge is the sanity check that zero old-slug
  references survive.
- **Recount totals by summing over the `categories` arrays, not the single
  `category` field** — after a rename that folded several web-analytics-adjacent
  buckets together, a category can legitimately balloon (e.g. 23→47) because
  many tools are members of it. Don't treat a large count as an error; it's the
  expected result of many-to-many aggregation. Report the per-category totals
  from the array-aware sweep, not the primary-field count.
- **Secondary-fit tools spanning buckets (e.g. product-analytics AND
  a-b-testing for PostHog) appear in multiple reassign lists — that is correct
  under many-to-many.** Append each; the curator/seed assigns the primary. Tools
  NOT in the reassign lists keep their single primary category (no phantom
  secondaries).

## Delivery close-out: PR handoff + vault status note

Research isn't done when the staging file is validated — the directory work often
includes a **code track** (schema migration, frontend rework) that the orchestrator
delegated to OpenCode. Close it out deliberately, and don't trust self-reports.

- **Hand the commit/push/PR to OpenCode with a short brief file, not a one-liner.**
  Write a `PR_BRIEF.md` (or similar) in the repo that enumerates EXACTLY which
  modified files AND which new files (migrations) to stage, and — critically —
  **lists the scratch files to EXCLUDE** (this repo accumulates loose
  `*_INSTRUCTIONS.md` / `*_BRIEF.md` docs that must not go in the commit).
  Tell it to stage those named paths, NOT `git add -A`/`.`. Then run
  `opencode run --auto "…"` from the repo's workdir in the background.
- **Verify the PR independently, never on the exit code or the hand-off summary.**
  After OpenCode reports done, run `git log --oneline -2` (confirm the expected
  commit SHA is HEAD) and `gh pr view <n> --json number,title,state,headRefName,url`
  to confirm the PR is actually OPEN against the right base. An exit-0 report
  with a fabricated/vague PR URL tells you nothing until `gh` confirms it.
  The commit subject should match the intended change and the staged files
  should be only the intended set (check `git status --short` for excluded
  scratch files left untracked, which is correct).
- **Write a vault status note for the project.** A trackable directory/research
  effort earns a concise markdown note in the vault's `docs/plans/` next to the
  related specs/briefs (not a throwaway). Include: date + project + repo/branch,
  a `status:` line, one-line per subsection of what was done (research counts,
  schema change, re-tag, delivery/PR URL), a final category-coverage table, the
  deliverable paths (`research/tools.json`, `research/logos/`, `research/notes/`),
  and a `- [ ] next steps` checklist (merge PR, seed-ingest drafts). Use a
  `uid:` frontmatter per vault convention, then re-run `ccc index` so it's
  semantically searchable. This is how a fresh session later finds "where did
  this leave off".

## Discovery via MCP-gated sources (e.g. SEO tooling)

Some strong discovery sources are **MCP-gated** (reached through the Pantheon
MCP hub / an orchestrator), NOT tools a leaf subagent can call directly.
Two patterns that sharply speed discovery:

- **Fetch SERPs to harvest URLs.** Run SEO-tool SERP queries for the exact
  category phrase (e.g. "user testing tools", "heatmap analytics software").
  The organic results surface the domains that actually rank — a tool ranking
  for a relevant query is a strong reality check. Pull URLs/domains from the
  results as candidates.
- **Find competitor domains.** Pick a well-known tool already in the directory
  (e.g. usertesting.com, hotjar.com) and use the SEO tool's competitor-domain
  lookups to discover the set of domains ranking against it — a rich candidate
  pool in the same space.

These are still **discovery only**: every URL/domain surfaced must still pass
the full verification workflow before becoming a listing.

**Gate MCP-gated discovery on ACTUAL hub availability, not the CLI registry.**
`pantheon mcp list` can show an MCP as mounted/healthy (`●`) while it is
actually `failed` at hub runtime and its tools are entirely uncallable —
`search` and `get_schema` then silently return nothing, which looks like "no
tools exist". Before dispatching (or when meta-search comes up empty), query
the authoritative hub status via
`execute("return await call_tool('pantheon_status', {})")` and read
`mounted_mcps` vs `failed_mcps` (e.g. `se-ranking` under `failed_mcps` with
`reason: connection_error`). If the source is down, fall back to plain
web-search/directory discovery — SE Ranking is a nice-to-have candidate
harvester, never a hard dependency. Verify availability first; do not burn
time guessing tool names against a dead mount.

### Tool-access routing (who holds which tool)

- **Web search/extract = Tavily** (or whatever single web credential is
  configured). It does NOT render JS pages or download binaries — use it for
  discovery + initial text extraction, NOT for site-browsing verification or
  logo downloads.
- **Full site browsing + binary logo downloads = browser + terminal toolsets.**
  Provision those on any agent that must visit a site or save a logo file;
  do not try to substitute the web backend for them.
- **MCP-gated sources are reached through the orchestrator, not leaf
  subagents.** If a subagent needs SERP/competitor data, it either (a) requests
  it and waits for the orchestrator to run the MCP calls and pass the resulting
  URLs/domains back, or (b) the orchestrator pre-bakes the SERP/competitor
  candidate list into the agent's brief before dispatch. Subagents must NOT
  assume the MCP source's tools are in their own toolset.
- **Live-backend dedup lookup is plain HTTP, not MCP.** The step-0 `EXISTING`
  fetch is a public-read REST call (`/api/collections/<c>/records`) reachable
  with terminal/HTTP tooling — no special credential needed.
- **Defaults are set — do not change web backend or MCP credentials as part of
  a research task.**

See `references/se-ranking-discovery.md` for the SE Ranking specifics
(200+ tool namespace, search-then-get_schema rule, exact tool names, SERP +
competitor-domain patterns).

## Verification discipline

- **No hallucination:** no invented stats, user-counts, or claims. Everything
  grounded in the browsed site.
- **Not defunct:** drop acquired-and-killed / dead products; note material
  pricing changes in the description or drop. Watch for these signals when
  visiting a site (they are common in the analytics/replay space):
  - **Brand migration banner**: e.g. Smartlook's homepage banner announcing
    "joined Cisco"/winding down its standalone SKU with explicit "End of Sale
    <date>" — if the timeline is recent/upcoming, omit (a renew-only product is
    no longer an adoptable tool).
  - **Domain redirect to a different product**: if `sessionstack.com` now
    serves PlaybookUX, the original named product is gone — omit it and note
    the redirect; do not list under the old name or the new one.
  - **Rebrand swallow** of an old tool into a research/agency suite (SessionStack →
    PlaybookUX; Smartlook → Cisco/Splunk observability; wave-4: **AB Tasty → VWO**) — a
    homepage "joining forces / new chapter" banner with a partner logo is the
    tell; if one half is already listed, omit the merged partner rather than
    double-list.
  - **A roundup candidate can be the OLD NAME of an already-listed tool.** Top-5
    "best tools" lists keep surfacing pre-rebrand names years after the rename
    (wave-5: "UsabilityHub" appears in current roundups but it renamed to Lyssna
    in Oct 2023 and Lyssna is already listed; sources even describe Lyssna as
    "the rebrand of the original fivesecondtest.com (later UsabilityHub)"). When
    a candidate looks like a known brand's former identity, confirm the lineage
    via the brand's own announce blog / PR / brand page and skip it as a
    duplicate — same product, new name — rather than adding a second entry.
    **Web roundups are NOT dedup evidence**; they lag renames by years.
  - **Domain won't resolve at all** — `browser_navigate` returning
    `ERR_NAME_NOT_RESOLVED` for the product domain (e.g. dora.run in wave 4)
    usually means the site is unreachable, not a transient blip; treat as
    unverifiable and omit unless a canonical landing page is found elsewhere.
    Confirm with `getent hosts <domain>` + `curl -sIL` — some web backends
    (Tavily) are a *resolver with opinions*: wave-5 `web_extract` on
    editorial-a11y.org returned **"Blocked: URL targets a private or internal
    network address"** while the domain genuinely failed `getent`/curl
    (`code=000`, `ERR_NAME_NOT_RESOLVED`). A "blocked/private-network"
    `web_extract` message can therefore mean the domain truly doesn't resolve —
    verify with the OS resolver before trusting either verdict.
  - **Domain lapsed into a parked registrar "claim your domain" page** — a
    `.co.uk`/`.com` held as a UK2/GoDaddy/Namecheap holding page (wave-5:
    `sortsite.co.uk` → UK2 "Domain names for less… Claim your web identity")
    signals the product's domain lapsed → treat as discontinued/omit, and only
    re-check the vendor's remaining product page before ever listing it.
  - **"Migrate to X" retirement banner**: a homepage CTA telling existing users
    to migrate accounts off the product (highlight.io → "Migrate your Highlight
    account to LaunchDarkly") means the standalone SKU is being retired even
    though the site still looks live. Treat as acquired-then-killed; omit.
  - **Cross-site death signal (competitor banner):** a RIVAL's "Tool X is
    shutting down — migrate to us free" campaign (e.g. Zonka's "Delighted Is
    Shutting Down, Migrate Surveys… for Free") is hard evidence Tool X is
    end-of-life even if you never loaded X's own domain. If several competitors
    run such a campaign, drop X from the candidate set and only re-instate it
    after confirming X is alive on its own domain.
  - **Standalone domain now hosts a parent-product sunsetting page**: tenon.io
    (an accessibility-testing API) shut down Aug 7 2023 and now serves a Level
    Access "Tenon Sunsetting" page telling customers to move to the parent — the
    domain still resolves, but the tool is gone. Always read the page, not just
    the 200. Wave-3 also confirmed **Heap** merged into **Contentsquare** (then
    already listed) — dropped as a duplicate rather than re-listed. A "still
    live-looking" domain is not evidence of an adoptable product.
  - **`web_extract` can miss a client-side redirect — confirm with the browser.**
    A text extractor (Tavily) can return the brand's *old* homepage while a real
    browser follows a redirect to the true destination. Case: Delighted's own
    domain (`delighted.com` → `qualtrics.com/delighted`) — web_extract served
    the full brand homepage; `browser_navigate` followed to the Qualtrics page
    stating "It's no longer available." For any suspect in a consolidating space,
    treat `browser_navigate` (which follows redirects) as the source of truth
    for redirect detection, not web_extract.
  - **Live site ≠ the product you think it is.** A domain that resolves to a
    *different, unrelated* business is a hard skip, not a verification pass.
    E.g. `insighto.io` (a session-replay contender in this space) now serves a
    Polish building/laser-survey company — check the actual page content, not
    just that the URL returned 200, before logging any field.
- **Skip validation is part of the run, not a failure of it.** Disqualifying a
  candidate (defunct, no-pricing, no-logo, unverifiable) is correct output.
  Record why it was skipped in `source_note`/notes so the orchestrator knows it
  was considered and rejected — this is distinct from forgetting to research it.
- **Unverifiable official source = omit, don't guess.** If a tool's own site is
  locked down (403) or the canonical/PDF/doc page can't be fetched and no
  official alternative exists, omit rather than fabricate a URL or logo. A
  well-known tool you can't verify counts as unverifiable for this pass.
- **Curated, not exhaustive:** hand-picked quality beats a raw scrape. If you
  wouldn't recommend it to a practitioner, cut it.
- **Quality over quantity:** no per-category cap; return as many vetted tools
  as found, but fewer correct listings beat volume of junk.

## Field-bar validation — batch it BEFORE writing, not iteratively

Before you hand the staging JSON over, run a single programmatic sweep over the
whole `tools` array and check EVERY entry, so field-bar violations are caught in
one pass instead of one-by-one (this session burned repeated patch cycles
fixing one over-long tagline at a time). Assert per tool:
- `pricing` ∈ enum; `category` ∈ allowed slugs; `website` starts `https://`;
  `logo` = `logos/<slug>.<ext>` and the file exists & is non-zero.
- All required keys present (name, slug, category, pricing, tagline,
  description, website, logo, best_for, key_features, tags, status, featured,
  featured_order, initial, card_color).
- `3 <= len(key_features) <= 6`, `2 <= len(tags) <= 6`.
- **`8 <= len(tagline.split()) <= 14`** — the single most common field-bar miss
  here; taglines run long. Fix all offenders in one edit.
- A good concrete validator lives in `scripts/validate-staging.py`.
  Call it with the staging file path; it reports every entry that fails without
  trusting the file to have already been checked.

## Reference

- `references/usefulusability-research-spec.md` — concrete worked example: the
  pocketbase-schema-matching staging spec written for the UsefulUsability
  directory (6 fixed categories, pricing enum, verification workflow, logo
  handling), useful as a copy-adapt template for the next directory project.
- `scripts/validate-staging.py` — one-pass field-bar validator for a staging
  JSON (category/pricing enums, required fields, key_features/tags counts,
  tagline 8–14 words, logo path→file resolution, in-file slug uniqueness).
  Run it before handing off so every entry is checked in a single sweep.
- `references/defunct-and-free-tool-detection.md` — worked wave-2 examples:
  retirement banners ("Migrate to LaunchDarkly" = highlight.io), domain
  redirect-to-different-product (SessionStack→PlaybookUX), live-but-wrong
  product (insighto.io → Polish building-survey firm), and open-source /
  government tools with no usable brand asset (IBM Equal Access, ANDI, PAC 3).
- `references/reconstructing-cutoff-deliverable.md` — worked reconstruction of
  a cut-off agent's missing staging JSON (newcat3): what the delegation log
  recovers vs. what must be re-verified live, the programmatic dedup sweep,
  and the two tooling gotchas (line-numbered `read_file`; broad-command denial).
