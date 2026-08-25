# Logo acquisition + verification — wave 5

Worked examples from the UsefulUsability wave-5 run. New techniques on top of
waves 3–4 (see `logo-acquisition-wave3.md` / `logo-acquisition-wave4.md`).

## favicon.ico → embedded full-size PNG (Ackee)

Ackee (self-hosted analytics) ships NO SVG and no standalone PNG brand asset — the
site is minimal and the header logo is styled text. The only asset is
`raw.githubusercontent.com/electerious/Ackee/master/dist/favicon.ico` (53KB).

The ICO *container* embeds a 256×256 PNG of the real brand mark (gradient circle
on a dark rounded square). Extract it instead of treating the ICO as "just a 16px
glyph":

```python
d = open("favicon.ico", "rb").read()
i = d.find(b"\x89PNG")  # locate embedded PNG magic
e = d.find(b"IEND") + 4  # IEND chunk end
open("ackee.png", "wb").write(d[i:e])  # -> valid 256x256 transparent mark
# dims via struct.unpack('>II', d[i+16:i+24])  -> 256 256  (>=256 meets the bar)
```

Earlier probing the ICO header separately told us a 256px entry existed
(`struct.unpack('<HHH', d[:6])`, dir-entry `w/h` bytes); but splicing the embedded
PNG directly is simpler and yields the real mark.

## JS-SPA site → GitHub repo `public/favicon.svg` (Excalidraw)

Excalidraw's homepage is a browser SPA; the header logo is an inline component,
and `excalidraw.com/og-image-3.png` is a marketing banner, not a logo. The repo
root `public/` held the only clean lockup:

`raw.githubusercontent.com/excalidraw/excalidraw/master/public/favicon.svg`
→ 1000×1000 SVG: white rounded-square with the Excalidraw hand-drawn mark.
1000px is fine for a card (white bg — keep on light cards).

Note `excalidraw.com/excalidraw-logo.svg` returned HTTP 200 with **SPA HTML**, not
SVG — the site's catch-all route served the shell. Don't trust a 200 on the site
for an asset URL; the repo is authoritative.

## Next.js frontend → `web/public/logo512.png` (Swetrix)

Swetrix header logo is an **inline `<svg>`** (5-dot indigo/navy "S" mark + the
wordmark as HTML text). The `favicon.ico` is small. The GitHub repo root had a
`web/` Next.js app whose `web/public/logo512.png` is the official 512×512
transparent mark:

`raw.githubusercontent.com/Swetrix/swetrix/master/web/public/logo512.png`
→ 512×512 transparent PNG (verified via PNG magic, not `file`, which is often
absent).

## PHP site → probe `.svg` variant of the `.jpg` (DubBot)

DubBot's homepage HTML references `_image/dubbot-primary-logo.jpg` (a raster). The
SAME base path serves an **official SVG**:

`https://dubbot.com/_image/dubbot-primary-logo.svg` → 304×74 wordmark, 12 paths.
A `dubbot-secondary-logo.svg` also exists. Quickly probed:
```
for e in svg png jpg; do curl -sL -o /tmp/x.$e -w "%{http_code}" dubbot.com/_image/dubbot-primary-logo.$e; done
```
Use the SVG over the JPG (no background, scalable).

## Defunct/omission signals confirmed this wave

- **`sortsite.co.uk` parked** → `web_extract` returned a UK2 "Domain names for
  less / Claim your web identity" holding page. The SortSite desktop a11y checker
  domain lapsed → omit (didn't even bother checking the vendor's remaining page,
  the park is the signal).
- **`editoria11y.org` unresolvable** → `web_extract` said `Blocked: URL targets a
  private or internal network address`; `getent hosts` → no DNS; `curl -sIL` →
  `code=000 / ERR_NAME_NOT_RESOLVED`. A genuinely real open-source tool (Princeton
  in-context CMS a11y checker) but the website is unverifiable in this environment
  → had to omit despite the tool being excellent. Lesson: a "blocked/private" web
  backend verdict can be a real-DNS failure; confirm with the OS resolver.

## Collision double-check pattern that kept it honest

After writing `agent12.json`, re-ran a programmatic collision sweep over ALL
sibling `agent*.json` + `tools.json` (+ the live PocketBase seed) collecting every
`slug` AND case-folded `name`, then checked my 5 chosen slugs for exact +
substring + name hits. Zero collisions. This is the "final cross-agent
collision re-check" section of the SKILL.md applied at depth.
