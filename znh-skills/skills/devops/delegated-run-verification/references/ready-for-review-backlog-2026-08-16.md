# Ready-for-review backlog pass — 2026-08-16 (16 cards → done)

Full walkthrough of promoting a ready-for-review backlog to done, used to build
the "Reviewing a backlog" section in the parent SKILL.md. The lesson: `progress:`
is not a reliable done signal; judge each card against its kind-specific
artifact.

## Permission note

Done-promotion is normally Zack-only in Obsidian, but the user can explicitly
delegate it ("work them through one by one, move to done if finished and
confirmed working/present"). When delegated, promote via `vault_board.py`
(single writer) with `update --path ... --status done --progress 100` — never
hand-edit card frontmatter.

## The cards and the evidence that made each one "done"

Scratch/code-backed (progress: 100, run log + on-disk deliverable):

- G6W3SA6F Christmas landing pages — 25 `output/*.json` + 25 `pages/*.md` +
  `landing_pages.json` + `landing_pages_summary.csv` +
  `christmas_cards_export_tracking.csv` in scratch/015.
- S4tnDmt3 Bulk christmas cards — 589-keyword cluster, SERP data, RESULTS.md in
  scratch/009.
- fZr6xxuc Enforce client gate — scripts/vault_board.py + test_client_gate.py
  (8 tests run by hand), client rendered in all base views.
- hluP4Zgb / bNpFTha1 / 4AcG1FJF herdr P3/P4/P5 — code changes +
  `KANBAN_RUNTIME=herdr` systemd drop-in present, VERIFICATION.md, 166 tests.
- EJ2o9HOu Orphaned mcp — REPORT.md + pushed branch feat/010.
- gSa4Pq89 Split opencode profiles — three `agents/*.md` (python, web-dev,
  wireframing) exist under ~/.config/opencode/.
- IYQq1TKE Thankbox page optimisation — 1416-row `data/keyword_plan.csv` +
  KEYWORD_PLAN.md in scratch/008.

Progress:0 cards — DO NOT reject on progress (all five genuinely shipped;
verified by grepping the live artifact, which these carry no run log for):

- nyemzNNy Handoff template — `opencode-handoff-template.md` +
  `scripts/vault_handoff.py` exist.
- feam6p0o ccc-search Enter-close — `Enter ... openResult also closes the
  modal` handler in plugin main.js.
- XwyQ0IPU ccc multi-column UI — `.ccc-search` left/right column classes in
  styles.css.
- OijoDKH0 Home dashboard — Search Console button + API_BALANCES file +
  KANBAN_FILTER_DIR in plugin files.
- E9IHf35J Vault librarian — `_report_rows` table + `trigger-note-processing`
  command (Mod+Shift+P) + `.librarian_history.jsonl` sidecar.

## Lesson

The reaper/scanner can leave cards in ready-for-review at progress:0 even when
the work is fully shipped (older feature/handoff cards). Do not bounce them back
on semantics alone — open the shipped artifact and judge. Only genuinely
unfinished ones stay. Promote in a batched loop, then confirm
`list --status ready-for-review` → 0 cards.
