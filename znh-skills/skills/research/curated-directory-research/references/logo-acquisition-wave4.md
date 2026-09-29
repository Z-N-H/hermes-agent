# Wave-4 logo acquisition & defunct-detection additions

Worked examples from a later directory wave (categories: user-testing,
surveys-feedback, session-recording). Builds on `logo-extraction-and-defunct-detection.md`
and `logo-acquisition-wave3.md`.

## Content-negotiation gotchas when curling logo assets

Brands increasingly serve logos through image-CDN / WAF front-ends that
content-negotiate by the request's `Accept` header. Two sharp traps hit curl:

1. **`?format=png` can still return webp.** Datadog's asset was
   `https://corp.dd-static.net/img/datadog_rbg_n_2x.png?format=png`. A curl with
   `Accept: image/avif,image/webp,...,image/*` (the list some browsers send)
   returned `image/webp` bytes → the file failed the PNG magic check. Fix: force
   the format explicitly with `-H "Accept: image/png"`. Always re-validate the
   magic number / `file` type, not just the `?format=png` in the URL.
2. **curl gets SPA HTML (HTTP 200, `text/html`) instead of the image — the asset
   is real, the headers are wrong.** Condens's logo at
   `https://condens.io/img/website_ui/logo.png` returned the Next.js index.html
   to a plain `curl -A "Mozilla/5.0"`, so it LOOKED like a 404/block. Sending the
   image `Accept` header won't always fix it (it still returned HTML). Reliable
   fixes that worked: (a) discover the true asset URL from the **rendered page**
   via `browser_get_images` (it reported the real `331×100` logo.png), then
   re-curl with the exact browser `Accept:
   image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8` + a
   `Referer:` + full Chrome UA — that finally returned `image/png`. Treat
   "HTTP 200 but wrong content-type" as a header/negotiation problem to solve,
   not as "asset missing".

## Inline-SVG header logo → capture with browser_console, not file download

Dovetail's nav wordmark is an inline `<svg>` (no downloadable file). The page
also ships `favicon.svg` (48×48 mark, dark rounded tile via CSS vars) — usable
as a low-quality official mark, but renders as a dark tile on a light card.
When the whole wordmark is only inline: pull the logo element from the DOM
(`document.querySelectorAll('a')` scanning `aria-label`/`href`, then
`logoEl.querySelector('svg').outerHTML`) via `browser_console`. Prefer a larger
element (header lockup) over a tiny nav icon; flag monochrome/small for the
curator.

## Monochrome brand-mark fallback for bot-blocked / white-only big brands

Qualtrics exposed only a `qualtrics-logo-white.svg` (`.cls-1 { fill:#fff }` —
invisible on white cards) and its colored SVG is bot-blocked. New Relic's site
gave no reachable file at all. When the brand's own site yields nothing usable
(everything white or behind a WAF) and the tool is otherwise an obvious
must-list, fall back to the **Simple Icons** monochrome brand mark:
`https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/<slug>.svg`
(e.g. `qualtrics`, `newrelic` → recognizable single-color Q / NR glyph). This is
a real, recognizable brand glyph, but it is NOT the brand's colored wordmark —
**flag it "low / monochrome, curator may re-source"** and say so in the notes;
don't ship silently as if it were the official colored lockup.

## Cross-site dead-competitor detection (VALUE: catch a death you never visited)

A competitor shutting down is often announced not on its own (soon-to-be-dead)
site but on a RIVAL's site running a "migrate to us free" campaign. Zonka
Feedback's homepage banner read *"Delighted Is Shutting Down. Migrate Surveys,
Data, and Workflows to Zonka for Free."* — that is hard evidence Delighted is
end-of-life even though we never loaded delighted.com. During discovery, if you
repeatedly see *"<Tool X> is shutting down — switch to us"* migration banners
on multiple competitors, treat Tool X as a defunct candidate and verify on its
own domain before ever listing it. This complements the existing "migrate off
the dying product's OWN homepage" signal.

## Other wave-4 skip observations

- **UserZoom** → now hosted on `usertesting.com` (UserTesting's platform);
  merged/shared-brand. If one half is already listed, omit the other (duplicate).
- **UX24/7** — a moderated user-research *services agency* (UK/global), not a
  self-serve software tool. In a tools directory, an agency/service whose value
  prop is "we can run studies for you" has poor field fit (no pricing page, no
  self-serve product) — omit unless the directory explicitly catalogs services.
- **Trymata** — homepage returned a WordPress `› Error` page (broken/stale CMS);
  treat a broken homepage as unverifiable and omit (product may be orphaned).
- **Yandex Metrica** — homepage behind SmartCaptcha (logo unobtainable) AND its
  core is full web-analytics (session-replay/Webvisor is secondary) — if your
  assigned category is session-recording and the analytics list already has
  replay-capable free tools, consider it a better fit for the analytics
  category or omit on logo-block.

## Validation lesson (re-emphasized)

`glob('agent*.json')` matches your own output file — when re-checking slug
collisions against sibling wave files, exclude your own file explicitly or every
slug you just wrote will falsely report as a collision. (Already noted in
SKILL.md; this wave hit it again and confirmed the fix.)
