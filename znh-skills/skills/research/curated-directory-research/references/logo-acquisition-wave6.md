# Logo acquisition — wave 6 (new-category pass: A/B testing, product/web analytics)

Worked channels landed while growing a UX-tools directory across its expanded
16-category taxonomy. These complement the wave-3/4/5 patterns and the
`inline-svg-logo-techniques.md` fallback chain.

## 1. Cookie-consent-CDN logos (OneTrust / cdn.cookielaw.org)

Many brands outsource their consent banner to OneTrust/CookiePro, and that
vendor also stores an **official brand PNG** on `cdn.cookielaw.org`.

- When the homepage nav only yields an inline/white `<svg>` (or nothing
  usable), the cookie-consent player is a legitimately-official logo host.
- Probe with `browser_console`:
  `document.querySelectorAll('img[alt*="Logo" i], img[src*="cookielaw"]')` → src
  is a `https://cdn.cookielaw.org/logos/<account>/<consent>/<asset>/<brand>-logo.png`.
- Worked: Heap's logo (`500×197` transparent PNG) pulled from
  `cdn.cookielaw.org/logos/8294609a-…/heap-logo.png`; alt text literally
  `"Heap Logo"`. Download with
  `curl -sL -A "Mozilla/5.0" "<url>" -o logos/heap.png`.

## 2. Strip the Next.js `/_next/image` optimizer; curl the CDN asset direct

Next.js/React marketing sites route `img src` through an image-optimization
proxy: `https://<site>/_next/image/?url=<urlencoded-unsigned-CDN-url>&w=384&q=75`.

- The `<img>.src` in the DOM is the proxy form. To get the raw file:
  - Read `document.querySelector('header a img, nav a img').src`; URL-decode
    the `url=` param; that decoded URL is the real asset.
  - `curl -sL "<decoded-cdn-url>" -o logos/<slug>.<ext>` (no `/_next/image`
    wrapper).
- **Do NOT trust the filename extension from where you fetched it.** Pendo's
  logo grabbed as `pendo.png` from `cdn.builder.io/api/v1/image/assets%2F…`
  came back as an SVG (`<?xml…?><svg … viewBox="0 0 216 50">`). Rename/validate
  by content, not by the name: if `head -c` shows `<?xml`/`<svg`, save as `.svg`.
- Worked: Pendo → builder.io asset under `pendo.io/_next/image/`; extracted the
  builder.io URL, curled it direct, validated it was an SVG, saved as `pendo.svg`.

## 3. Very large inline nav SVG → regex-extract from the page HTML, don't hand-copy

When a brand's whole nav lockup is a single huge inline `<svg>` (Woopra's is
~12KB, `class="logo" viewBox="54 0 507 242"`, black `fill="#020202"` path data),
pulling the full `outerHTML` through `browser_console` and pasting it into a
`write_file` is wasteful and error-prone.

- `curl -sL -A "Mozilla/5.0" "<homepage>" -o /tmp/page.html`
- In the session runner, regex it out and write it with the file-write tool:
  `re.search(r'<svg[^>]*class="logo"[^>]*>.*?</svg>', html, re.S)` → `write_file`.
- Works because the inline SVG is present verbatim in the served HTML for these
  sites (no JS needed). Confirm it closes (`</svg>`) and has path shapes.
- Keep using `write_file`, never a terminal `python3 - <<'PY'` heredoc, for this
  write (users block terminal-based file writes).
- If the inline SVG only appears after JS render, fall back to the
  `browser_console` + `write_file` path (existing guidance).

## 4. Cloudflare "Verify you are human" CAPTCHA caveat

With no residential proxy configured, a Cloudflare interstitial can render a
clickable `checkbox "Verify you are human"` (ref like `@e9`). **Clicking it is
not a guaranteed solve**: it can be clicked and the page still stays on
"Just a moment... / Performing security verification" indefinitely (observed on
abtasty.com; also `title` stayed `Just a moment...` with a `?ki-cf-botcl=1`
query guard).

Rules for this class:
- Timebox the attempt (a couple of clicks + short waits). Do not fight it for
  many turns.
- If it will not clear AND you could not pre-pull an official asset, follow the
  existing decision bar: **no usable logo → omit the tool**, and if the tool has
  already merged into an already-listed partner (AB Tasty → VWO), omit as a
  duplicate rather than double-list. Record why in `source_note`.
- Do NOT substitute a third-party favicon/logo-directory glyph to dodge the wall.

## Reassign-form note

New-category agents on the taxonomy-expansion track commonly emit a top-level
`reassign: { "<new-category>": [existing-slug, …] }` map alongside their new
`tools` — the machine-readable form of the SKILL.md `belongs-here` flag. Both
spellings carry the same signal for the re-tag step; either is fine as long as
the notes say which key the orchestrator should consume.
