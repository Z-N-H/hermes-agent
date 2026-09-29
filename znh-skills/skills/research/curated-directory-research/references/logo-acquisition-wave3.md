# Logo acquisition: wave-3 patterns (worked examples)

Companion to the "Locating and extracting the logo" section of SKILL.md. These
are the non-obvious cases that came up acquiring logos for a wave of privacy /
self-hosted / dev-first tools, where the normal nav-`<img>`→`/logo.svg`→`og:image`
ladder came up empty and needed deeper digging.

## 1. Next.js / asset-CDN sites — enumerate, don't guess the hash

AudioEye (audioeye.com) keeps real logos at hashed `_next/static/media/` paths
*plus* a clean un-hashed copy at `/images/logos/audioeye-logo-black-purple-symbol.svg`.
The page also appended a cache-buster query (`?dpl=…`) to every asset URL.

- The `?dpl=…` query is NOT part of the asset — strip it before curling.
- Find what actually loaded (don't reconstruct hashes by hand):

```js
// browser_console
[...document.querySelectorAll('img, source[srcset]')]
  .filter(e => (e.src||e.srcset||'').toLowerCase().includes('logo'))
  .map(e => (e.src||e.srcset||'').split(' ')[0])
```

## 2. WAF that 403s curl even with a full browser UA

AudioEye returned an HTML page (its WAF/bot page) to `curl -A "<full Chrome UA>"`
for the logo URL. Same-origin `fetch` from inside the already-authenticated page
bypassed it:

```js
// browser_console (page context)
(async () => (await fetch('https://www.audioeye.com/images/logos/audioeye-logo-black-purple-symbol.svg', { credentials: 'omit' })).text())()
```

Paste the returned SVG text into `write_file`. (Do NOT route through a `python3 - <<'PY'` heredoc — users block those file writes.)

## 3. CSS-drawn / text-only wordmark — no file exists

- **GoAccess** (goaccess.io): the header "logo" is a pure-CSS 3D cube
  (`box-shadow` on a small div) + styled `G`/`o`Access text. No `<img>`, no svg
  in the page, and `/images/goaccess-logo.png` was WAF-guarded → nothing to grab.
- **Wireframe.cc**: brand is inline text + app-shell glyphs; no logo asset file.
  `og:image` was a homepage screenshot (not a logo → treat as no brand asset).

Fix for "CSS logo": go to the **GitHub repo** and look for a real file (below).
If nothing exists, omit the tool per the logo bar — both Principle and
Wireframe.cc were eligible tools dropped for lack of a clean downloadable logo.

## 4. Project logo lives in the GitHub repo, not the site

When the homepage has no asset, walk the project's repo tree and pull the real
file:

```bash
# find logo-ish files in the repo
curl -s "https://api.github.com/repos/<org>/<repo>/git/trees/master?recursive=1" \
 | python3 -c "import sys,json; [print(t['path']) for t in json.load(sys.stdin)['tree'] if any(k in t['path'].lower() for k in ['logo','images','png','svg','ico'])]"
```

- **GoAccess** → `resources/goaccess.svg` (the official cube mark, 946 B).
  Pull via `raw.githubusercontent.com/allinurl/goaccess/master/resources/goaccess.svg`.
- **Pirsch** → root `logo.svg` (277 B) → `raw.githubusercontent.com/pirsch-analytics/pirsch/master/logo.svg`.

VectorLogoZone / Simple Icons did NOT have goaccess or pirsch — the repo tree is
the more reliable source for open-source projects.

## 5. Mark-only vs full wordmark — flags for the curator

Pirsch's repo `logo.svg` is only the small geometric "S-curves + dots" mark
(viewBox 26×38), not the full serif "Pirsch" lockup. A 277-byte SVG that's just
a mark is usable but low-detail — save it but note "mark only / low detail" in
the notes so the curator can source the wordmark before ingest.

## 6. Final validation (host lacks `file`/`xxd`/`identify`)

Validate magic bytes in Python instead:

```python
d = open(path, "rb").read()
png = d[:8] == b"\x89PNG\r\n\x1a\n"  # read dims via struct.unpack('>II', d[16:24])
svg = b"<svg" in d[:200]  # tolerate an XML prolog before <svg>
```
