# Diagnosing an unstyled site at a tailnet subpath

## Symptom

A framework site (Astro, Vite, Next export, etc.) served through a tailnet
subpath mount renders completely unstyled — default serif font, block layout,
no cards/colours. HTML content is present but looks like raw browser output.

## Root cause (most common)

The static build emitted **root-absolute asset URLs** (`/assets/app.css`),
which only work when the site is served at the domain root. Under a subpath
mount (`/usefulusability`), those URLs resolve to the **tailnet root** — which
`tailscale serve` is usually proxying to a *different* local service (e.g.
`/` → 127.0.0.1:9999). The browser fetches the wrong origin's response, and
CSS/fonts/images fail.

## Diagnostic ladder (fast, definitive)

Do these in a browser console (via browser_navigate to the tailnet URL + a
`browser_console` expression). Stop as soon as one answers it.

1. **Look at the page** (browser_vision / screenshot). Completely unstyled =
   CSS not applied at all (vs partly applied = a specific rule problem).

2. **What does the linked stylesheet resolve to?**
   ```js
   [...document.querySelectorAll('link[rel=stylesheet]')].map(l=>l.href)
   ```
   If hrefs are `https://HOST/...` (no subpath) while the page URL has a
   subpath — that's the bug. They should be
   `https://HOST/<subpath>/...`.

3. **Is the served CSS valid when fetched WITH the subpath?**
   ```js
   fetch('/<subpath>/<css-path>').then(r=>r.text()).then(t=>({
     ct: r.headers.get('content-type'), bytes: t.length,
     rules: t.split('{').length - 1,
     hasUtility: t.includes('.<some-class-the-html-uses>')
   }))
   ```
   Valid + present = serving fine; the mismatch is the URL the page uses.

4. **Does the browser apply any of it?**
   ```js
   const cs=getComputedStyle(document.body);
   ({display:cs.display, fontFamily:cs.fontFamily, bg:cs.backgroundColor})
   ```
   `display:block`, `Times New Roman` = zero CSS applied. Correlate with
   `[...document.styleSheets].map(s=>s.cssRules.length)` (0 rules = nothing
   parsed — the wrong file was loaded).

5. **Check the font/@font-face refs too** — the CSS itself can contain absolute
   URLs (`url(/assets/font.woff2)`) that break the same way even after the
   main stylesheet path is fixed.

## The fix

Make the framework build emit **subpath-aware base paths** at build time:

- **Astro**: set `base` (and `site`) in `astro.config.mjs`. Best done env- or
  flag-driven so the real domain-root deployment isn't broken by a preview
  value — e.g. `base: process.env.ASTRO_BASE ?? '/'` and build the preview
  with `ASTRO_BASE=/usefulusability` (or a small script). Rebuild and re-serve;
  `tailscale serve` mount itself is untouched.
- **Vite**: `base` in `vite.config.js` similarly.
- **Static (http.server)**: remount at the root if free, or rewrite paths.

Knock-on effects to check after fixing base: API base URLs baked into the
frontend (e.g. PocketBase `pb.ts`), canonical/OG tags, sitemap, robots.txt,
and any JS asset paths.

## Related separate 403: `preview.allowedHosts`

Serving a Vite/**Astro preview** server through tailscale can return
`403 Blocked request. This host ("bazzite.centaur-perch.ts.net") is not
allowed.` — Vite host-checks the `Host` header, and `tailscale serve` forwards
the tailnet hostname. Fix: add the tailnet hostname to `preview.allowedHosts`
(via the `vite.preview` key in `astro.config.mjs`, since Astro apps often have
no standalone `vite.config.js`), rebuild, restart the preview. Diagnose with a
plain `curl` — the 403 body literally names the config key and value to add.

## Checklist

- [ ] stylesheet `<link>` href must include the subpath
- [ ] `@font-face` / asset `url()` in the CSS must include the subpath
- [ ] verify in a REAL browser (screenshot + computed style), not just curl
- [ ] confirm deep routes (`/tools`, `/search?q=...`) render styled too
- [ ] confirm the domain-root build still works (or document the env/flag to
      produce it) — don't hardcode a preview-only base
