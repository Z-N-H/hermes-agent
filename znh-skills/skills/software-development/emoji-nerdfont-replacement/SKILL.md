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

**Execution time**: On a tree the size of `hermes-agent` (~2,350 replacements
across 122 files) the script takes **2–3 minutes**. Run it in the background
with `notify_on_complete=True` so you can keep working while it runs, then
poll the log:

```bash
curl -sL https://raw.githubusercontent.com/ryanoasis/nerd-fonts/master/glyphnames.json -o /tmp/nf.json

# Background — preferred for large trees
cd /path/to/hermes-agent && python3 scripts/replace_emojis.py /tmp/nf.json . \
  > /tmp/replacement.log 2>&1 &
# ...poll tail -f /tmp/replacement.log until "Total replacements" appears

# Foreground — fine for small trees (< 30 s expected)
python3 scripts/replace_emojis.py /tmp/nf.json /path/to/hermes-agent
```

## The mapping table (verified codepoints)

See `references/nerdfont-codepoints.md` for the full table. Codepoints
verified against Nerd Fonts v3.4.0 (April 2025). Some entries had to be
corrected from older guides — see pitfalls section 1.

A constant-module variant lives at
`~/.hermes/hermes-agent/hermes_icons.py` — defines `ICON_OK`, `ICON_WARN`,
`ICON_GEAR`, etc. as named string constants for new code.

## The preferred API: `NerdFontIcons` lookup class

Since 2026-06-20, `hermes_icons.py` has been rewritten as a lazy lookup
class backed by the committed `glyphnames.json`. New code should **never**
hardcode raw `\uXXXX` escapes; use lookups instead:

```python
from hermes_icons import NerdFontIcons

# Direct lookup by full key
icon = NerdFontIcons.get("fa-check")  # -> "\uf00c"
icon = NerdFontIcons.get("md-robot")  # -> "\U000f06a9"

# Reverse lookup: emoji -> Nerd Font codepoint (for migration tooling)
icon = NerdFontIcons.get_by_emoji("✅")  # -> "\uf05d"
icon = NerdFontIcons.get_by_emoji("⚠️")  # -> "\uf071" (handles VS16)

# Fuzzy search
keys = NerdFontIcons.find("check")  # -> ['fa-check', 'fa-circle_check', ...]

# List everything
all_keys = NerdFontIcons.keys()  # -> 10,765 entries
```

The class is thread-safe, parses JSON lazily on first access, and caches
for the process lifetime. Back-compat aliases (`ICON_OK`, `ICON_WARN`, etc.)
remain so existing imports keep working.

See `references/nerdfont-icons-api.md` for the full API surface.

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

### 3. Scope is huge — don't underestimate; execution time is real
A "remove emojis" task in Hermes Agent touches ~2,300 occurrences across
~120 source files. The replacement script alone takes **2–3 minutes** on a
tree this size. Run it in background mode with `notify_on_complete` so you
can keep working:

| Bucket                            | Approx occurrences |
|-----------------------------------|---------------------|
| `cli.py` (status bar, banners)    | ~100                |
| `hermes_cli/*.py`                 | ~100                |
| `agent/*.py` (display, conv)      | ~80                 |
| `tools/*.py`                      | ~50                 |
| `run_agent.py`, compressors       | ~50                 |
| `locales/*.yaml` (17 files)       | ~1,800              |
| `scripts/*.sh`, `setup-hermes.sh` | ~50                 |
| `plugins/*.py` (bundled)          | ~50                 |
| `~/.hermes/plugins/*`, skins      | variable            |

A single targeted patch on `cli.py` will NOT satisfy the user. They see
emojis everywhere, not just the status bar.

### 4. Tests will break — update assertions with actual codepoints
`tests/agent/test_display_emoji.py` and `tests/cli/test_cli_status_bar.py`
assert against literal emoji strings. After replacement, these fail. You MUST
update the test fixtures to use the **actual Nerd Font codepoints** that the
script wrote (not just re-run pytest and hope).

Update pattern:
```python
# Before
assert result == "⚡"
# After
assert result == "\uf0e7"  # the actual codepoint now in source
```

Use `grep` to find remaining emoji in tests, then replace with the matching
Nerd Font codepoint:
```bash
cd hermes-agent && grep -rnP '[\x{1F300}-\x{1F9FF}\x{2600}-\x{26FF}\x{2700}-\x{27BF}]' tests/ --include='*.py'
```

For variation selectors (e.g. `⚠️` vs `⚠`), the replacement script normalises
both to the same codepoint, but test strings may use either. Check both forms.

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

### 9. Test assertion fixing has a concrete recipe
After replacement, tests that assert against literal emoji strings will
fail. The pattern is predictable:

| Old assertion | New assertion | File |
|---|---|---|
| `assert result == "⚡"` | `assert result == "\uf0e7"` | `tests/agent/test_display_emoji.py` |
| `assert "✓ 42s" in text` | `assert "\uf00c 42s" in text` | `tests/cli/test_cli_status_bar.py` |
| `assert "🗜️ 3" in text` | `assert "\uf066 3" in text` | `tests/cli/test_cli_status_bar.py` |
| `assert "⚕" in text` | `assert "\uf0f1" in text` | `tests/cli/test_cli_status_bar.py` |
| `assert "🎤 Ctrl+B" in text` | `assert "\uf130 Ctrl+B" in text` | `tests/cli/test_cli_status_bar.py` |

Use Python, not `sed`, for the replacement — `sed` can mangle Unicode
escape sequences depending on locale. Read the file in UTF-8, do string
`.replace()` in Python, write back.

### 10. Emojis not in ICON_MAP need manual addition
The script only replaces emojis explicitly listed in `ICON_MAP`. If you
grep and find remaining emojis like `✕`, `⚔`, or `🔇`, add them to
`ICON_MAP` and re-run, or patch the specific lines manually. Common
omissions are mathematical symbols (`✕`, `✓`, `✗`) and lesser-used
pictographs (`🔇`, `🎙️`) that aren't in the default 50-item map.

### 11. Distinguish emoji failures from environment failures
After replacement you may see test failures that *look* emoji-related but
aren't. Example: `ModuleNotFoundError: No module named 'httpx'` in
`tests/cli/test_cli_status_bar.py::TestCLIUsageReport`. The test failed
because a dependency was missing, not because the emoji replacement was
wrong. Check the actual error message before re-running the replacement
script.

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

### 12. Do not modify built-in skin presets
The user may say "only change the custom skin" or "don't touch the defaults".
Respect this. The built-in `_BUILTIN_SKINS` in `skin_engine.py` are **off
limits**. Only edit the user's custom skin YAML in `~/.hermes/skins/*.yaml`.
Then replace hardcoded `⚕` fallbacks across `cli.py` and `hermes_cli/*.py` with
`get_active_brand_icon()` so the CLI dynamically reads the active skin's icon
instead of ignoring it. See `references/dynamic-brand-icon-lookup.md`.

### 13. Hardcoded fallbacks bypass skin overrides
Even when a custom skin sets `response_label: " Hermes"`, the CLI will still
show `⚕` if any code path hardcodes the glyph. Common traps:
- `_print_banner()` uses `"⚕ NOUS HERMES..."` when `skin_name == "default"`
- `_get_status_bar_text()` prefixes model name with `"⚕ "`
- `_get_status_bar_fragments()` uses `" ⚕ "` as a literal tuple element
- Response box fallbacks use `"⚕ Hermes"` in `except Exception:` blocks
- Wizard/setup banners in `config.py`, `tools_config.py`, `gateway.py`, etc.

Audit with `grep -rn '"⚕' hermes_cli/ cli.py` and fix every hit outside
`_BUILTIN_SKINS`. Do not assume the skin YAML alone is sufficient.

## Verification

After running the script:

1. **Syntax check** every modified `.py`:
   ```bash
   python3 -m py_compile $(git diff --name-only | grep '\\.py$')
   ```
2. **Re-grep for remaining emoji** in target files (using same exclusions as the replacement script):
   ```bash
   grep -rnP '[\x{1F300}-\x{1F9FF}\x{2600}-\x{26FF}\x{2700}-\x{27BF}]' \\
       --include='*.py' --include='*.sh' --include='*.yaml' --include='*.yml' \\
       hermes-agent | \\
       grep -v -E '(venv|.venv|tests|optional-skills|node_modules|\\.git|__pycache__|site-packages|gateway/platforms|plugins/platforms)'
   ```
3. **Fix test assertions** that reference literal emoji. Search tests:
   ```bash
   grep -rnP '[\x{1F300}-\x{1F9FF}\x{2600}-\x{26FF}\x{2700}-\x{27BF}]' tests/ --include='*.py'
   ```
   Replace each with the corresponding Nerd Font codepoint that now appears
   in the source (e.g. `✓` → `\uf00c`, `🗜️` → `\uf066`).
4. **Run the test suite** and confirm zero emoji-related failures:
   ```bash
   pytest tests/agent/test_display_emoji.py tests/cli/test_cli_status_bar.py -v
   ```
5. **Visual check**: start `hermes` and confirm the status bar renders
   icons (not boxes / tofu). If boxes, the user doesn't have a Nerd
   Font installed — stop and tell them.
6. **Verify completion**: If you still see emojis in UI chrome (status bar,
   prompts, banners), the replacement did not complete successfully.
   Re-run the script and check for any errors in the output.
   or database connection failures are NOT emoji-related — don't re-run
   the replacement script for those.
6. **Verify completion**: If you still see emojis in UI chrome (status bar, prompts, banners),
   the replacement did not complete successfully. Re-run the script and check
   for any errors in the output.

## Files in this skill

- `references/nerdfont-codepoints.md` — full emoji → codepoint mapping
  table with set prefix (fa / md / cod / oct / seti / dev)
- `references/dynamic-brand-icon-lookup.md` — `get_active_brand_icon()`
  helper, full file list of hardcoded `⚕` locations, and replacement recipe
- `references/hermes-branding-icons.md` — TUI vs CLI branding locations
  and the "do not modify default skins" rule
- `scripts/replace_emojis.py` — bulk replacement script (run once)
- `references/previous-mistakes.md` — 2026-06-14 failure transcript and
  why this skill now exists
- `references/test-fix-recipe.md` — concrete assertion replacements for
  the Hermes test suite after running the bulk script
