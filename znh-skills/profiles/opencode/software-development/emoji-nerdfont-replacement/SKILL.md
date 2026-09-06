---
name: emoji-nerdfont-replacement
description: 'Replace emojis in Hermes Agent source code with Nerd Font Private Use Area codepoints for terminal display. Use when user reports emoji rendering issues in CLI, asks to remove emojis from output, or when building UI chrome that needs cross-terminal consistency. Covers the full pipeline: verifying codepoints against the official Nerd Fonts metadata, bulk-replacing across the source tree, and what to skip (gateway/platforms outbound messages, plugin/platforms adapters, tests, kaomoji/spinner data, vendored deps).'
version: 2.0.0
author: Hermes Agent
tags: [emoji, nerdfont, replacement, unicode, terminals, hermes, codepoints, pua]
---

# Emoji → Nerd Font Replacement (Hermes Agent)

Systematic, codepoint-verified replacement of emojis with Nerd Font PUA
codepoints across the Hermes Agent source tree. Replaces ~50 commonly used
emojis across ~120 source files in one pass.

## When to use this

- User says "remove emojis", "no emojis in output", "I can still see emojis
  in the UI", or "the previous task didn't work"
- Building UI chrome (status bar, prompts, banners, tooltips, banners,
  loading spinners) that needs to render consistently across terminals
- Resuming a previous emoji-removal task that was reported "done" but
  visibly incomplete (very common — see pitfalls section 6)

## When NOT to use this

- **Outbound messages to messaging platforms.** `gateway/platforms/*` and
  `plugins/platforms/*` send emoji as part of Telegram/Discord/Slack/
  Signal/Matrix/Feishu/etc. messages. Those platforms render emoji
  natively; PUA codepoints will look like tofu to recipients.
- **Decorative ASCII-art / kaomoji / spinner animation data.** Examples:
  the kaomoji pool in `agent/display.py` (`◕‿◕`, `★ω★`, etc.), the
  moon-phase spinner in the same file, and the brain-emoji animation
  frames. Replacing these destroys the aesthetic without fixing any
  actual UI bug.
- **Vendored dependencies**: `venv/`, `node_modules/`, `site-packages/`,
  anything under `.git/`.
- **Test fixtures.** Tests assert against literal emoji strings.
  Replacing the strings breaks the tests. Fix tests in a separate pass.
- **Documentation files** (`*.md`, `*.rst`) unless the user explicitly
  asks. Docs render fine in markdown viewers with emoji support; the
  problem is terminal output.

## The canonical replacement script

Self-contained Python script at `scripts/replace_emojis.py`. It:
- Loads the official `glyphnames.json` from
  `github.com/ryanoasis/nerd-fonts` (the authoritative codepoint list)
- Builds a regex from a list of `(emoji, nf_set, icon_name)` tuples
- Walks the source tree, skipping the paths above
- Writes replacements in-place with a per-file count

Run:
```bash
curl -sL https://raw.githubusercontent.com/ryanoasis/nerd-fonts/master/glyphnames.json -o /tmp/nf.json
python3 scripts/replace_emojis.py /tmp/nf.json /path/to/hermes-agent
```

## The mapping table (verified codepoints)

See `references/nerdfont-codepoints.md` for the full table. Codepoints
verified against Nerd Fonts v3.4.0 (April 2025). Some entries had to be
corrected from older guides — see pitfalls section 1.

A constant-module variant lives at
`~/.hermes/hermes-agent/hermes_icons.py` — defines `ICON_OK`, `ICON_WARN`,
`ICON_GEAR`, etc. as named string constants for new code.

## Pitfalls (real mistakes that have been made — do not repeat)

### 1. Many icon names in older guides are WRONG
These do not exist in the actual font; some were renamed in FontAwesome v6:
- `nf-fa-times_circle` does not exist; use `nf-fa-circle_xmark`
- `nf-fa-search` does not exist; use `nf-fa-magnifying_glass`
- `nf-fa-volume_up` does not exist; use `nf-fa-volume_high`
- `nf-fa-volume_mute` does not exist; use `nf-fa-volume_xmark`
- `nf-fa-mobile` does not exist; use `nf-fa-mobile_screen`
- `nf-fa-tools`, `nf-fa-wrench`, `nf-fa-hammer` do not exist as separate icons; use `nf-fa-screwdriver_wrench`
- `nf-fa-cog` does not exist (renamed in FontAwesome v6); use `nf-fa-gear`
- `nf-fa-tint` does not exist; use `nf-fa-droplet`
- `nf-fa-burst` does not exist; use `nf-fa-explosion`
- `nf-fa-chart-bar` is wrong syntax; use `nf-fa-chart_bar` (underscore)
- `nf-fa-trash` does not exist; use `nf-fa-trash_can`
- `nf-md-chart-bar`, `nf-md-trending-up` are wrong; use `nf-md-chart_bar`, `nf-md-trending_up`

ALWAYS verify against the official `glyphnames.json`. Do not trust blog
posts or wiki pages.

### 2. Python `\U` escape requires EXACTLY 8 hex digits
- `\uXXXX` — 4 hex digits, codepoints up to U+FFFF
- `\UXXXXXXXX` — 8 hex digits, any codepoint

`\U000f05c` (7 chars after `\U`) is malformed and raises SyntaxError.
For 4-digit codepoints use `\uXXXX` or `\U0000XXXX`.

### 3. Scope is huge — don't underestimate
A "remove emojis" task in Hermes Agent touches ~700 occurrences across
~120 source files:

| Bucket                            | Approx occurrences |
|-----------------------------------|---------------------|
| `cli.py` (status bar, banners)    | ~100                |
| `hermes_cli/*.py`                 | ~100                |
| `agent/*.py` (display, conv)      | ~80                 |
| `tools/*.py`                      | ~50                 |
| `run_agent.py`, compressors       | ~50                 |
| `locales/*.yaml` (12 files)       | ~110                |
| `scripts/*.sh`, `setup-hermes.sh` | ~50                 |
| `plugins/*.py` (bundled)          | ~50                 |
| `~/.hermes/plugins/*`, skins      | variable            |

A single targeted patch on `cli.py` will NOT satisfy the user. They see
emojis everywhere, not just the status bar.

### 4. Tests will break
`tests/agent/test_display_emoji.py` and similar tests assert against
literal emoji strings. After replacement, these fail. Either:
- Run `pytest` and update the test fixtures to use the new codepoints, OR
- Add a test-mode shim that re-maps PUA codepoints back to emoji before
  assertion

Do NOT claim the task is "done" without running the test suite.

### 5. Nerd Font is required for rendering
PUA codepoints render as blank boxes / tofu on a non-Nerd-Font terminal.
The replacement is a NET NEGATIVE if the user doesn't have one. Verify
their terminal font BEFORE doing the swap:

```bash
fc-list | grep -i nerd
```

If empty, point them at https://www.nerdfonts.com/font-listings. Common
options: Cascadia Code NF, JetBrainsMono Nerd Font, FiraCode Nerd Font,
Hack Nerd Font, Meslo Nerd Font, Iosevka Nerd Font.

### 6. The previous "task done" was wrong
On 2026-06-14, an earlier session claimed emoji removal was complete. It
wasn't. Only `cli.py`, `toolset_distributions.py`, and a handful of others
were touched — and `toolset_distributions.py` was corrupted with mixed
Unicode escapes (`\U000f05c` instead of `\uF05C`, causing SyntaxError).
The user noticed emojis still in the UI on the next session. If you're
resuming a prior task, ALWAYS verify with grep first — don't trust the
prior completion message.

### 7. VS16 (variation selector) handling
Many emoji in source code include `\ufe0f` (variation selector-16, the
emoji presentation hint). The replacement regex MUST accept this
optional suffix. Example: both `⚠` (U+26A0) and `⚠️` (U+26A0 + U+FE0F)
are the same logical emoji and must map to the same codepoint.

### 8. The "kawaii" personality string is content, not UI chrome
`cli.py` line ~433 has a personality prompt that contains kaomoji
(`(◕‿◕)`, `ヽ(>∀<☆)ノ`). These are character-level content the model
emits in chat, not terminal output. Leave them alone unless the user
specifically asks to rewrite personality text.

## Verification

After running the script:

1. **Syntax check** every modified `.py`:
   ```bash
   python3 -m py_compile $(git diff --name-only | grep '\\.py$')
   ```
2. **Re-grep for remaining emoji** in target files (using same exclusions as the replacement script):
   ```bash
   grep -rnP '[\\x{1F300}-\\x{1F9FF}\\x{2600}-\\x{26FF}\\x{2700}-\\x{27BF}]' \\
       --include='*.py' --include='*.sh' --include='*.yaml' --include='*.yml' \\
       hermes-agent | \\
       grep -v -E '(venv|.venv|tests|optional-skills|node_modules|\\.git|__pycache__|site-packages|gateway/platforms|plugins/platforms)'
   ```
3. **Run the test suite** and update broken assertions:
   ```bash
   pytest tests/agent/test_display_emoji.py tests/cli/test_cli_status_bar.py -v
   ```
   **Important**: Tests that assert against literal emoji strings will fail after replacement. You MUST update the test fixtures to use the new PUA codepoints or add a test-mode shim.
4. **Visual check**: start `hermes` and confirm the status bar renders
   icons (not boxes / tofu). If boxes, the user doesn't have a Nerd
   Font installed — stop and tell them.
5. **Verify completion**: If you still see emojis in UI chrome (status bar, prompts, banners),
   the replacement did not complete successfully. Re-run the script and check
   for any errors in the output.

## Files in this skill

- `references/nerdfont-codepoints.md` — full emoji → codepoint mapping
  table with set prefix (fa / md / cod / oct / seti / dev)
- `scripts/replace_emojis.py` — bulk replacement script (run once)
- `references/previous-mistakes.md` — 2026-06-14 failure transcript and
  why this skill now exists
