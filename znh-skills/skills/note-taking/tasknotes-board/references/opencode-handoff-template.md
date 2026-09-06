# Handoff: <short task title>

<!--
Hermes → OpenCode structured handoff. Fill every section, then create the
card with vault_handoff.py (see the tasknotes-board SKILL.md). The script
refuses the handoff if any section is missing or empty — no placeholders,
no "TBD". If you can't fill a section, the task isn't ready to hand off.
-->

## Goal

One paragraph: the single deliverable OpenCode must produce, stated as an
outcome ("a script that does X", "file Y updated to Z"), not an activity
("look into", "investigate").

## Context & Files

Everything OpenCode needs that it can't be expected to know:

- Absolute paths to relevant files/dirs (one per line, with a few words on
  why each matters)
- Linked notes / uids from the vault (`[[wikilink]]`, `uid: xxxx`)
- Key facts established before handoff (decisions already made, dead ends
  already ruled out)

## Constraints

Hard rules for the run — things that would make the work wrong even if the
goal is met:

- e.g. "Do NOT git commit", "don't touch plugin X", "stdlib only",
  "follow existing style in scripts/"

## Acceptance Criteria

Every box must be independently verifiable by reading the result — no
subjective criteria ("looks good", "works well"):

- [ ] First verifiable outcome
- [ ] Second verifiable outcome

## Verification Steps

Exact commands or checks OpenCode (or a reviewer) runs to prove the
acceptance criteria, e.g.:

1. `uv run pytest tests/test_foo.py` — passes
2. `grep -c "section" output.md` — returns 6

## Out of Scope

Explicit exclusions so the run doesn't sprawl — adjacent problems noticed
but NOT to be fixed here, future work, anything OpenCode might otherwise
helpfully wander into.
