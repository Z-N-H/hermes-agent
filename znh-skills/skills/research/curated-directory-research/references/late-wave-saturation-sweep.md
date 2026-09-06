# Late-wave saturation sweep (wave 6+ methodology)

When a directory is already large (100+ entries across all categories), a
"wave 6 sweep" is a different animal from wave 1. The obvious top-tier names in
every category are gone. What still works:

## 1. Quantify per-category totals FIRST, then prioritize the thinnest

Before discovery, load the canonical staging file's `tools` array and tally
`category_totals`. Budget your research effort by deficit, not by flat rotation:

- The 1–2 **thinnest** categories are where genuinely-new finds still exist.
  Put most of your discovery + verification there.
- **Saturated** categories (roughly ≥20 solid, well-covered entries) rarely
  yield a new *excellent* tool — sweep them for completeness but expect 0.
- This mirrors the existing "rising bar at depth" rule with an operational
  twist: *deficit-driven coverage, not equal-all-categories coverage.*

## 2. Admit 0 for saturated categories — and SAY so

Returning `category_totals: {user-testing: 0, prototyping: 0, ...}` for a
category is correct output in a late wave, not a failure. State it explicitly in
the summary/notes: "saturated — swept, nothing genuinely-new + excellent
admitted." This is the concrete form of the brief's "returning zero is
acceptable" instruction.

Do not pad a saturated category with a marginal tool to avoid a 0; a padding
entry is worse than an honest 0.

## 3. Write a per-category saturation statement

In the wave notes, for EVERY category record your verdict (saturated vs. still
gappy) and, if gappy, what the residual gap is. This tells the next wave where
to look and, importantly, what NOT to re-research:
- Example residual-gap phrasing: "session-recording not fully saturated —
  still room for a dedicated hosted mobile-app replay niche, and emerging
  AI-session-summary tools."
- The orchestrator folds these into the next wave's brief as the discovery
  steer (a tactical corollary of the "known-bad compound knowledge" rule).

## 4. Open-source / academic / practitioner-standard FREE tools are late-wave gold

Late waves are NOT only about finding newer startups. Gap-filling often comes
from established open-source, academic, or community-standard tools that were
never considered before because they're not "SaaS that appears in roundups":

- **Color Oracle** (color blindness simulator; open source, Windows/Mac/Linux)
  — fills the design-time *simulation* niche in accessibility.
- **NVDA** (Non-Visual Desktop Access; open-source Windows screen reader) —
  fills the *manual assistive-tech QA* niche in accessibility (teams run real
  screen-reader checks without JAWS licensing costs).
- These genuinely satisfy the `free` pricing enum ("genuinely free at useful
  scale"), which roundup SaaS rarely does.

Source them the same way: official site verified, features/pricing logged from
the browsed site, no invented stats. `website` = official project/product site
(e.g. `colororacle.org`, `nvaccess.org`), not a download mirror or GitHub alone.

## 5. Good-candidate screening at depth (what to reject)

Keep a running "considered and rejected" note so the orchestrator knows it was
swept, not missed. Common late-wave reject classes seen in practice:
- **Tool that's one feature of a big busy self-host platform** (replay buried
  amid deploy/analytics/email) — not distinctive enough for a *usability* directory.
- **Recently-acquired + host product sunsetting** (e.g. highlight.io → LaunchDarkly:
  "Migrate your Highlight account to LaunchDarkly" banner). Reject on continuity risk.
- **Commercial platform overlapping an already-admitted trio** (third/fourth
  scanner when two strong monitors are already in).
- **Minor free web utilities** (small single-purpose online simulators) with
  lower credibility than an established academic/open-source tool filling the
  same niche — prefer the credible one.

## Worked example (UsefulUsability, wave 6)

Admitted 4: `color-oracle` (accessibility, free), `nvda` (accessibility, free),
`accessibility-cloud` (accessibility, freemium), `uxlens` (session-recording,
freemium). Category totals moved: accessibility 21 → 24, session-recording
18 → 19. The other four categories (~23–27 entries) returned 0 — swept, saturated.
Saturation verdict stayed: session-recording gappy (mobile-replay + AI-summary
niche open); accessibility now closed (screen-reader + simulator + multi-engine
monitor covered); the rest closed.
