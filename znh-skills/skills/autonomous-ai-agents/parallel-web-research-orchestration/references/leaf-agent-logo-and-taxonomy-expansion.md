# Leaf-agent logo download & taxonomy-expansion checklist (worked recipe)

From the 2026-08-08 UsefulUsability "new categories" run. The orchestrator
skill covers the PM side; this is the **leaf-agent** recipe for (a) reliably
downloading a logo and (b) producing a `reassign` block when growing the
taxonomy. Reproduce with modifications.

## Acceptable-outcome bar (from the brief)

- Official site reachable (https), browsed via web_extract/real browser;
  `name/slug/category/pricing/tagline/description/website/logo/best_for/k
  ey_features/tags` logged from what was actually seen — no invented stats.
- `pricing` ∈ `free|freemium|paid|free_trial`; `category` is one exact slug.
- Logo downloaded from the brand's OWN asset, not a directory cover.
- No DB/CMS writes — staging JSON only.

## Logo download — validate every byte, not the extension

`curl -sL` exits 0 even on an error page. Check magic bytes after every fetch,
looping over candidate paths until one passes:

```bash
# try candidates in order; first magic-byte pass wins
for url in \
  "https://<host>/favicon.png" "https://<host>/favicon.ico" \
  "https://<host>/assets/img/logo.svg" "https://<host>/logo.svg" \
  "https://<host>/logo.png" ; do
  curl -sL -A "Mozilla/5.0" -o candidate.bin "$url"
  sig=$(head -c 4 candidate.bin | od -An -tx1 | tr -d ' ')
  case "$url" in
    *.svg) head -c 5 candidate.bin | grep -q '<?xml\|<svg' && { cp candidate.bin out.svg; break; } ;;
    *.png) head -c 4 candidate.bin | grep -q $'\x89PNG' && { cp candidate.bin out.png; break; } ;;
    *.ico) head -c 4 candidate.bin | grep -q $'\x00\x00\x01\x00' && { cp candidate.bin out.ico; break; } ;;
  esac
done
# catch og:image social banner (NOT a logo) and apple-touch-icon separately
curl -sL -A "Mozilla/5.0" <host> | grep -io 'rel="icon" href="[^"]*"\|apple-touch[^>]*href="[^"]*"\|og:image[^>]*content="[^"]*"'
```

## Header inline-`<svg>` logo extraction (the case curl can't reach)

Many modern product sites (Optimizely, Amplitude, Heap, Convert, Woopra,
Countly, Aurelius, …) do NOT expose the logo as a downloadable image file at
all. The brand mark is an **inline `<svg>` embedded in the header**, usually
inside the logo/home link, and there is no `/logo.svg` or `og:image` worth
grabbing. The curl-magic-byte loop will miss these entirely → fall back to the
real browser and pull the SVG out of the DOM:

```js
// in browser_console on the site's homepage:
const a = document.querySelector('a[aria-label*="home"], a[aria-label*="Home"], a[href="/"]');
const svgs = a ? Array.from(a.querySelectorAll('svg')) : [];
// pick the brand wordmark: largest viewBox width, ignore menu/hamburger icons
const big = svgs.filter(s => { const v = s.getAttribute('viewBox')||''; return v && parseFloat(v.split(' ')[2]) > 40; });
return (big[0] || svgs[0]).outerHTML;   // copy + write to logos/<slug>.svg
```

- The rendered header usually holds TWO svgs: a small-screen mark (e.g.
  `class="xl:hidden"`) and a full wordmark (e.g. `xl:block`). Grab the
  **wordmark** for a directory card; the mark-only variant is a fallback.
- Optimizely's was the wordmark under `a[aria-label="Optimizely Home"]`; Amplit
  ude's nav-svg was the largest `viewBox` in `header, nav`. Adjust the selector
  per site; the "largest svg in the home link / nav" heuristic is reliable.
- Save via `write_file`, not a shell heredoc — SVG is large and write_file
  lints it.

### `fill="currentColor"` is colorless without a CSS context

Inline header SVGs frequently use `fill="currentColor"`, which inherits text
color — and renders BLACK (or invisible) when the paste loses the page's CSS
(card/logos on light background). Before saving a DOM-extracted logo, replace
every `currentColor` with a concrete brand hex so it stands alone:

- If the site's accent/brand colour is visible elsewhere (Amplitude dark
  `#22222E`), substitute that.
- Otherwise default to a near-black (`#000`/`#1a1a1a`); the curator can
  re-tint. A common approach: sed/`patch` `fill="currentColor"` → `fill="#22222E"`
  in the extracted SVG text before writing the file.

## Verify the brand is the brand — name→domain is NOT trustworthy

Do not assume `https://<name>.com` is the product. This run hit three real
traps that cost verification cycles before being caught:

- **getmarvin.com is a window-and-door manufacturer**, not the UX-research
  tool "Marvin". Always re-resolve the product via web_search (correct:
  `heymarvin.com`) BEFORE browsing/logo-downloading — a well-known brand name
  may be squatted by an unrelated company.
- **enjoyhq.com now redirects to usertesting.com** — EnjoyHQ was absorbed into
  an already-listed product. Eat the redirect: if the "obviously right" domain
  serves an already-listed/acquired product, do NOT list a second entry; note
  it as absorbed in the notes file and move on.
- **abtasty.com = Cloudflare-blocked AND merged with VWO** (already listed
  under Wingify). When a candidate both overlaps an existing record and its
  logo is unreachable, skip: a belongs-here note is cheaper than fighting a
  bot challenge for a duplicate.

Rule: browse and read the site FIRST (does the offering/brand match?), and
re-check the target of any redirect, before paying the logo fetch. A candidate
name matching an expected domain is a hypothesis, not verification.

## Quality bar for the LOGO asset

- Prefer an **SVG** brand/header mark, else transparent PNG ≥256px.
- Do NOT ship an `og:image` social banner as the logo.
- If the only official asset is a small favicon-glyph (many indie tools expose
  only 16/32px PNG/GIF), still save it but mark **quality low** in the notes so
  a human curator can source a proper brand kit before ingest.
- Verify the file decodes (non-zero, correct magic bytes) before recording the
  `logo` path.
- **Re-verify at the very end**: in a shared `logos/` dir a concurrent agent or
  build step can overwrite your downloaded PNG with a WebP/HTML of the same
  name. Re-run the byte check on every referenced logo just before finalizing,
  and restore the correct asset if it changed.

## Workspace hygiene / concurrency

- Never reuse a shared workspace while earlier agents are still writing — name
  your output uniquely (e.g. `agent16.json`, `logos/<slug>.<ext>`).
- **Re-run the cross-sibling collision check at the VERY end, not just at
  start.** A shared staging dir may gain NEW `agent*.json` files mid-run: in
  the 2026-08-08 new-categories run, `agent14.json` landed after this agent
  started and already owned **9** of the exact tools I'd researched and staged
  (Optimizely, Statsig, GrowthBook, Convert, Kameleoon + Amplitude, Heap,
  Pendo, Woopra). Pre-flight dedup didn't catch it; only a final scan of every
  `agent*.json` + `existing_tools` + live DB did. Consequence: drop the shared
  entries from your file and find distinct fillers (e.g. Instapage/Unbounce/
  Omniconvert for A/B testing, Usermaven for product analytics) rather than
  shipping duplicate records. Build the check so it compares *slug AND name*
  against ALL sibling outputs, last write wins.
- When the main bucket's canonical tools are taken by a sibling, push into
  adjacent-but-distinct sub-fits (landing-page A/B, ecommerce CRO, attribution
  + product analytics) to keep the category filled without duplicating.
- Do not `rm` files in a shared dir you did not create; other agents may still
  reference them. Before deleting anything stray, grep the sibling staging
  JSONs (`grep -l <name> agent*.json`) to confirm no one references it.
- `file` may be absent on the box; use magic-byte checks instead of relying on
  it.

## Taxonomy expansion → emit a `reassign` block

To add NEW categories to a live curated set, the leaf agent output should carry
a block naming which EXISTING slugs belong in each new category, plus the
counts of newly-added tools:

```json
{
  "category_totals": { "typography": 4, "colour-palettes": 5, "colour-accessibility": 2 },
  "reassign": {
    "typography": [],
    "colour-palettes": [],
    "colour-accessibility": ["colour-contrast-analyser", "stark", "wave", "audioeye", "color-oracle"]
  },
  "tools": [ /* new records, category ∈ new slugs */ ]
}
```

Leaves categories with no existing members as `[]` — that signal tells the
curator there is nothing to re-tag. The `audioeye` "partly" case (tool that is
primarily one category but strongly belongs in the new one too) is worth a
"partly" note in the notes file so the human decides the primary relation.
