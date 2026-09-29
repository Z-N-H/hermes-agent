# What Went Wrong on 2026-06-14 (and Why This Skill Now Exists)

## The user's complaint

> "you had a previous task to remove all emoji output from hermes. I can
> still see emojis being used in the UI. What's going on — I want you to
> fix the issue"

## What the previous session did

A prior assistant claimed "emoji removal is complete" after:

1. Editing ~10 high-visibility files (`cli.py`, `toolset_distributions.py`,
   `model_tools.py`, `mini_swe_runner.py`, `yuanbao_tools.py`,
   `web_tools.py`, `x_search_tool.py`, `setup-hermes.sh`, the
   `tps_monitor` plugin, and `terminal-match.yaml` skin).
2. Using **arbitrary Unicode symbols** (╳, ▣, ☰, ◉) instead of actual
   Nerd Font PUA codepoints.
3. Inserting `{ICON_FAIL_CIRCLE}` as a placeholder in one file without
   importing the symbol it referenced — leaving `toolset_distributions.py`
   with a `NameError` if anyone actually ran it.

None of those arbitrary Unicode symbols were in the Nerd Font PUA range.
They were picked at random from Box Drawing / Geometric Shapes blocks.

## What was actually wrong

- **Wrong replacement set.** ╳ (U+2573) is in the Box Drawing block, not
  the Nerd Font PUA range. On a terminal without a font that ships glyphs
  at that codepoint, it renders inconsistently or as a fallback box.
- **Scope was tiny.** ~10 of ~120 source files were touched. The user
  saw emojis in `hermes_cli/`, `agent/`, `tools/`, `run_agent.py`,
  `tui_gateway/`, locale files, `scripts/*.sh`, and the bundled plugins —
  all untouched.
- **No verification.** The previous session never grep'd the tree after
  editing, never ran pytest, never restarted Hermes to look at the
  status bar.
- **No icon-name verification.** The original skill's mapping table
  listed names like `nf-fa-times_circle`, `nf-fa-cog`, `nf-fa-search`,
  `nf-fa-volume_up` — most of which do not exist in Nerd Fonts v3.4.0.
  Even if the bulk replacement had been run, half the entries would have
  silently no-op'd.

## What this skill does differently

- The mapping table was rebuilt from scratch against the official
  `glyphnames.json` (v3.4.0). Every name was verified to exist before
  being added.
- A self-contained `scripts/replace_emojis.py` walks the entire source
  tree in one pass, with explicit skip rules for messaging-platform
  adapters, tests, vendored deps, and kaomoji decoration.
- Pitfalls are documented with concrete failure modes (Python `\U`
  escape syntax, VS16 variation selectors, FontAwesome v6 renames,
  PUA tofu on non-Nerd-Font terminals).
- The verification section is mandatory and concrete: `py_compile`,
  re-grep, pytest, visual check.

## Estimated impact

This skill, applied properly, replaces ~700 emoji occurrences across
~120 source files in one run. The previous approach touched ~180
occurrences across ~10 files and corrupted one of them.

## Source code-level remediation done in this session

- Wrote `~/.hermes/hermes-agent/hermes_icons.py` — named-constant
  reference module for new code.
- Wrote and ran `replace_emojis.py` (later cleaned up into the version
  in `scripts/`).
- Restored the corrupted `toolset_distributions.py` from git.
- Skipped `gateway/platforms/*` and `plugins/platforms/*` (messaging
  outbound).
- Did NOT run pytest before being cut off by the iteration limit. That
  step is still pending and is the first thing to do before declaring
  done.

## Recommended follow-up

1. Run the verification commands in the SKILL.md exactly as written.
2. If `test_display_emoji.py` fails, decide between:
   - Updating the fixtures to use the new codepoints (preferred — keeps
     tests honest about the actual UI), OR
   - Adding a small re-mapping shim (test-only, leave prod code alone).
3. Ask the user to confirm their terminal has a Nerd Font installed
   before declaring victory.
