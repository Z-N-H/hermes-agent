# Logo extraction & defunct-tool detection — worked examples

Session provenance: UsefulUsability accessibility + session-recording research
pass (2026-08). Extracted 12 SVG logos across 6+ different site stacks, and
rejected 2 tools that turned out defunct/rebranded. Later waves (prototyping +
analytics-heatmaps, 2026-08) added presskit-ZIP extraction, the white-logo trap,
and the og:image distinction.

## Why `browser_get_images` alone is not enough

On three consecutive major product sites the homepage nav logo was an inline
`<svg>` that the accessibility tree / `browser_get_images` did not list at all:

- **Stark** (`getstark.co`) — logo found at `nav a[href="/"] svg` (874 chars),
  a single-color "S" mark with `fill="currentColor"`.
- **FullStory** (`fullstory.com`) — the wordmark at `svg[aria-label="Fullstory Logo"]`
  (130x25, `<path fill="#000" …>`).
- **LiveSession** (`livesession.io`) — Webflow; wordmark inlined in
  `.brand-logo.w-embed svg` (128x20, black text + a blue `#0A4ED6` glyph path).

Direct-file candidates appeared via `browser_console` querying `og:image` /
`link[rel="icon"]` / `apple-touch-icon` / header imgs:
- Siteimprove logo: `header img[src*="siteimprove"]` →
  `…/rebrand2025/siteimprove_ai_logo_plum_gradient.svg`
- UXCam: `nav img` → `/logo.svg` (`<img src="/logo.svg" alt="Blue UXCam logo" …>`)
- Wave: banner img → `/img/wavelogo.svg`
- Mouseflow: theme path → `…/assets/images/mouseflow-logo.svg`
- PostHog / OpenReplay / Accessibility Insights / Lighthouse / Pa11y: direct
  `.svg` URLs found in extracted page HTML.

## Small single-colour mark → add brand fill

Stark's 32x32 "S" path used `currentColor`, so on a transparent card it would
render invisibly. Fix: root it at a larger `viewBox` (256x256) and pin
`fill="#6C5CE7"` (their purple). Codegen from the browser copy is fine — keep
the path `d` verbatim.

```svg
<svg width="256" height="256" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path fill-rule="evenodd" clip-rule="evenodd" d="…(verbatim from outerHTML)…" fill="#6C5CE7"></path>
</svg>
```

## Pitfall: the blocked terminal python write

Attempting `curl` + `python3 - <<'PY'` (regex-extract the inline SVG from the
fetched HTML and write `livesession.svg`) was **BLOCKED by the user** — terminal
python-heredoc file-writes are not accepted for authoring assets. The
command-line `curl -o <slug>.svg <url>` for verbatim downloads was fine; for
anything transcribed/authored the flow is `browser_console` → full `outerHTML`
→ `write_file`. Lesson: pipe verbatim downloads through curl; hand-authored
content through write_file.

## Truncation hazard

My first `livesession.svg` was hand-transcribed and got the giant black text
path truncated mid-`d` (it ended "...l-.983 1.96" instead of the full path),
producing a broken logo. Always write from the complete `outerHTML` captured
from the DOM, and verify the file with `head -c` after writing.

## Presskit ZIP logo packages (added 2026-08, prototyping wave)

When a homepage shows only an inline/white SVG, open the reachable
`/presskit` or `/brand` subpage (often linked in the footer as "Brand assets" /
"Press kit"). Many brands host multi-colour horizontal lockups as **ZIP
packages on their own S3/CDN**, which give the true brand mark instead of
guessing a fill colour:

- Justinmind: `presskit/horizontal-logo-color.zip` (S3) → unzipped a 620×428
  multi-colour `justinmind-logo-color.png` — far better than retinting the white
  inline SVG. `curl -sL -o x.zip <url> && unzip -o -q x.zip`.
- The presskit lists colour / inverted / B/W / stacked variants so you can pick
  the right one per card background.

## White / dark-mode-only logos — the blank-card trap (added 2026-08)

Header `<svg>`s from dark-themed product sites are frequently `fill="#fff"`
white (Rive's logo glyph, VWO's dark variant, Matomo's nav logo). Saved verbatim
against a white directory card they render as an empty/blank image. Detection:
open the saved file in a browser (`browser_navigate file:///…`   →
`browser_vision`); a blank/white canvas means it's a light-on-dark asset.

Fixes, in order:
- Fetch the dark-on-light variant from the presskit / `/brand` page if present
  (Matomo ships `logo_matomo-horizontal-light@2x.png` — the *light* variant is
  for dark backgrounds; prefer a colour/on-white lockup).
- Else rewrite the path fill to a dark brand hex (`#2F2F4A`-style) and
  **vision-verify the saved file** — an SVG that renders on the vendor's dark
  nav can be invisible on your light card.

## Combined post-merger header lockup (added 2026-08)

Post-joint-venture brands may serve a **combined multi-product lockup** as their
header logo (VWO + AB Tasty after their merger: one ordered SVG showing both
wordmarks). It IS the official current header brand, so it's usable, but flag it
for the curator (`vwo.svg` in the notes) in case they prefer a VWO-only mark.
This is distinct from the product-level co-brand substitution case below.

## og:image — useful only when it's a brand mark (added 2026-08)

`og:image` is a real logo ONLY when it renders a clean brand mark/lockup with no
UI chrome, e.g. Origami Studio's OG card (white origami crane on a flat blue
gradient) — that's a legitimate low-quality slot. When `og:image` is a product
dashboard screenshot or marketing collage, treat it as "no brand asset" and fall
through to the presskit/`/brand` page instead. Vision-verify before using.

## Logo sanity checklist after every save

- `head -c 20` starts with `<?xml` or `<svg`.
- File size meaningful (full wordmark ~5–15 KB; tiny 600 B files are usually
  icons or error pages — pa11y's 641 B mark and stark's 914 B mark are genuine
  but low-fidelity; flag them for the curator).
- `curl -o` with `-A "Mozilla/5.0"` — bare curl 403s on several sites.
- SVG viewBox preserves aspect ratio (a width/height mismatch silently
  distorts — e.g. an SVG authored at 24×24 with a 428×389.11 viewBox needs
  `preserveAspectRatio="xMidYMid meet"` + matching width/height or it crops).

## Bot-protected brand asset → server-side favicon-proxy fallback

Sometimes the site's own bot/human challenge gates the logo even though an
`<img>` tag names it (UXtweak's `uxt-logo-horizontal-c.svg` on wave 2 of the
UsefulUsability run):
- raw `curl -A "Mozilla/5.0"` returns HTTP **202 with an EMPTY body** for the
  asset (challenge swallows it); Googlebot UA gets the same.
- the browser renders a CAPTCHA "Let's confirm you are human" puzzle, not the
  homepage — cannot be reliably passed by an agent.

**Workaround that worked:** favicon proxy services fetch on THEIR side, so they
bypass the site's challenge and return the official brand favicon as an image:
- `https://www.google.com/s2/favicons?domain=<host>&sz=256` (best res)
- `https://icons.duckduckgo.com/ip3/<host>.ico` (small fallback)
- (direct `logo.clearbit.com/<host>` occasionally DNS-fails; don't rely on it)

This is a LOW-QUALITY fallback. Nuance vs the "never use a favicon glyph" rule:
a third-party GENERIC icon is never acceptable, but pulling the SITE'S OWN
favicon brand mark through a proxy when the real asset is bot-blocked is a
reasonable low-quality fallback — save it as `<slug>.png`, flag it for the
curator, and note the exact blocker (the real wordmark SVG is unreachable, not
nonexistent) so the curator can source the full wordmark. ALWAYS confirm with
`vision_analyze` that the proxied image is the correct brand mark (shapes +
colours), not a generic placeholder — confirmation worked for UXtweak's yellow
hexagon + chevron.

## Lottie-JSON header logo (Webflow animated-brand site)

A Webflow site can render its nav brand as an animated Lottie `.json`
(e.g. Optimal Workshop's `Optimal3-logo.json`) instead of a static image — the
DOM has NO SVG/PNG brand asset to save and `currentSrc` is empty. When the
header logo is a `.json`/Lottie, fall back to the site's own
`link[rel="icon"]` / `favicon.svg` brand mark (URL visible in raw HTML). It is
low-fidelity (a 32px mark) but official; save it, flag for the curator.

## Inline-SVG brand lockup → wrap to standalone file

When the header brand is an inline `<svg>` with no static image asset (e.g.
Featurebase), extract `svg.outerHTML` via `browser_console`, wrap it with the
`<?xml?>` + `<svg width height viewBox fill="#BRANDHEX">` header (replacing
`fill="currentColor"` paths with the brand hex so it renders standalone), and
write with `write_file`. See the earlier inline-SVG sections — same rule: keep
every path `d` verbatim, never hand-truncate.

## Acquisition-adjacent overlap — owned by an already-listed competitor

A live, un-killed product can still be dropped because it now co-brands with a
tool already in the directory: UserInterviews' header reads "User Interviews by
UserTesting®" (part of UserTesting, Inc.), which would look like a duplicate of
the existing `usertesting` listing — so it was swapped for a distinct recruiting
panel (Respondent). When a candidate's parent appears in `EXISTING`, check the
header/footer co-branding; if it reads as a sibling/rebrand of an existing
entry, substitute a genuinely distinct tool rather than listing the sister.

## Defunct-tool detection that worked

- **Smartlook** (`smartlook.com`) — homepage was a "Future of Smartlook" banner:
  "joined Cisco", End of Sale 31 May 2026, renewals stop Aug 2026, paid support
  ends ~Aug 2027, folded into Splunk "Digital Experience Analytics". → omit.
- **SessionStack** (`sessionstack.com`) — resolved straight to PlaybookUX (a
  recruiting/unmoderated-interview research suite). The session-recording tool
  no longer exists. → omit, note the redirect.
- Checklist: if a "best tools" roundup says a tool is excellent but its own site
  shows a wind-down banner or a redirect, trust the live site over the roundup.
