# Defunct & free-tool detection — worked wave-2 examples

Sourced from a wave-2 pass over the accessibility and session-recording
categories. These are real detection cases; reuse the pattern, not the names.

## Retirement / acquired-then-killed signals (site still looks live)

**Deliverable: check the actual homepage content, not just that the URL 200s.**

- **highlight.io** — homepage carried a prominent banner: *"Migrate your
  Highlight account to LaunchDarkly. Learn more on our blog."* The code is
  Apache-2.0 open source and the site looks alive, but the standalone product
  is being retired (swallowed into LaunchDarkly). Treat the banner as
  acquired-then-killed: omit, even though it ranks and is talked about.
- **Smartlook** — "Smartlook has joined Cisco!" banner with an explicit
  End-of-Sale / End-of-Contract-Renewals / Last-Day-of-Support /
  platform-decommissioned timeline (e.g. decommission 30 Sep 2027). A product
  you can no longer buy is not adoptable → omit.
- **SessionStack** — `sessionstack.com` now serves **PlaybookUX** entirely
  (domain redirect to a different product). The original named tool is gone.
  Do not list under the old name OR the new one.
- **Delighted** — the brand's *own* domain (`delighted.com`) redirects to an
  acquirer subpage that keeps the name (`qualtrics.com/delighted`) and states
  "It's no longer available." Owned-domain → parent `/brand-name` redirect is
  acquired-then-killed, even though a text-extractor (`web_extract`) initially
  returns the brand's old homepage — text extractors can serve a rendered/cached
  brand page while a real browser follows the client-side redirect. Use
  `browser_navigate` (it follows redirects) as the redirect-detection source of
  truth, not web_extract, for consolidating analytics/replay names.

Takeaway: when a "top session replay" or "top analytics" roundup surfaces a
name, still browse the vendor homepage yourself. The analytics/replay space is
consolidating fast and roundups are full of half-dead brands.

## Live site but a DIFFERENT product — the hardest trap

- **insighto.io** — was a session-replay contender; the domain now resolves to
  a Polish building / laser-survey company (`insighto - Inwentaryzacja
  budowlana i pomiar laserowy`). URL returns 200 with real content, but it is
  the wrong product entirely. Always read the rendered page (browser) and
  confirm the brand/offering matches what you were researching before logging
  `name`/`tagline`/`website`.

Takeaway: a 200 response proves reachability, not product identity. For tools
whose memory/roundup reputation may be stale, verify with a real page browse.

## Right category, wrong remembered pitch

- **Kadoa** — carried into the run from context as a "privacy-first session
  replay" tool, but on browsing the homepage it is a web-scraping /
  data-extraction platform for finance (datasets, ETL, warehousing — no session
  recording at all). Not defunct — a different product in a different category.

Takeaway: when a candidate is sourced from memory/context rather than fresh
discovery, verify its category/positioning against the actual rendered page, not
the remembered pitch. A remembered one-liner can pair a real product with the
wrong category; skip it if it doesn't fit the category you're filling.

## Unverifiable official source → omit, don't guess

- **PAC 3 (PDF Accessibility Checker, by the PDF Association)** — the canonical
  `pdfa.org/resource/accessibility-checker-pac-3/` page returned 403 Forbidden
  (and is blocked in some extraction backends), and no official GitHub repo
  surfaced. Well-known in the a11y community, but with no verifiable official
  URL/logo, it is omitted rather than given a guessed link or fabricated asset.

Takeaway: fame does not make a listing verifiable in this pass. No official
site reachable → no listing (and say so in `source_note`).

## Open-source / government tools with no usable brand asset

Returning "low" quality vs omitting is a judgment call. General rule: a bad
logo is grounds to omit unless the parent-brand lockup is legitimate.

- **IBM Equal Access** (open source, GitHub `IBMa/equal-access`, 768★, active):
  has NO standalone product logo — but ships under the IBM brand, so using the
  official IBM 8-bar blue logo is a legitimate "low quality slot, curator
  decides" call (flag it in notes; don't ship silently).
- **ANDI** (SSA Accessibility Name & Description Inspector): only opaque UI
  screenshots exist (a black toolbar with the wordmark at ~3% of frame) — no
  transparent logo, no official SVG, no ≥256px PNG. A directory card cannot
  carry that. Omit on logo-quality grounds despite the tool being genuinely
  useful and free.
- **Colour Contrast Analyser (CCA)**: no dedicated product brand, but it's
  produced by Vispero (formerly TPGi); using the vendor's official
  `vispero_logo.svg` wordmark is the acceptable path (same parent-brand logic
  as IBM Equal Access) — flag as low, don't drop, because a respected logo
  exists even if it's the parent's mark.

Takeaway for the logo hyperlink: when a tool has no logo of its own but a clear
upstream vendor/parent brand, using the parent lockup is defensible (flag it);
when the only asset is a screenshot, omit the tool. See
`references/logo-extraction-and-defunct-detection.md` for extraction mechanics.

## Cross-agent collision caught at final re-check

- **Glassbox** — selected for session-recording this pass, but a sibling
  (agent5, analytics-heatmaps) had already registered `glassbox`. The final
  re-read of ALL sibling files caught it. Remedy: drop and substitute an
  equivalent verified candidate (this session used **Fullview**, a
  privacy/support replay tool), never double-list.

## Validator behavior worth repeating

The tagline word-count (`8 <= len(tagline.split()) <= 14`) was the most
repeated adjustment — several entries came out at 15–18 words. Run
`scripts/validate-staging.py` once at the end and fix all offenders in a
single batch instead of patching them one at a time.
