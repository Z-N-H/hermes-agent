---
name: hermes-skin-customization
description: Customize Hermes Agent's terminal appearance by editing skin YAML files — change the icon next to "Hermes" (response_label), the prompt symbol, the goodbye message, colors, spinner, and other branding. Use when the user wants to change how Hermes looks in their terminal, e.g. "change the icon next to Hermes", "the icon shows as a blank box", "customize the response banner", "make Hermes look different", "swap the skin".
---

# Hermes Skin Customization

Hermes's terminal appearance is controlled by YAML skin files under `~/.hermes/skins/`. The active skin is named in `~/.hermes/config.yaml`:

```
skin: <skin-name>
```

Skin files are plain YAML — no rebuild, no plugin, no code edit. Edit the file and restart Hermes.

## Where things live

- **Config**: `~/.hermes/config.yaml` (sets `skin: <name>`)
- **Skin files**: `~/.hermes/skins/<skin-name>.yaml`
- **Bundled defaults** ship in this same folder: `terminal-match.yaml`, `message-text-icon.yaml`, etc. Both ship out-of-the-box; only one is active.

To create a new skin, copy an existing YAML, change its `name:`, and point `config.yaml` at it. Don't edit a built-in unless you intend to keep it forever.

## Skin YAML structure

```yaml
name: <unique-id>                    # must match the filename stem
description: <human description>

colors:                              # hex color codes (QUOTE THEM — bare # is a YAML comment)
  banner_border: "#8ae234"
  banner_title:  "#fce94f"
  banner_accent: "#ef2929"
  banner_dim:    "#888a85"
  banner_text:   "#ffffff"
  ui_accent:     "#729fcf"
  ui_label:      "#34e2e2"
  ui_ok:         "#8ae234"
  ui_error:      "#ef2929"
  ui_warn:       "#fce94f"
  prompt:        "#ffffff"
  input_rule:    "#8ae234"
  response_border: "#8ae234"
  session_label:   "#888a85"
  session_border:  "#888a85"
  status_bar_bg:        "#2e3436"
  voice_status_bg:      "#2e3436"
  completion_menu_bg:   "#2e3436"
  completion_menu_current_bg:    "#3465a4"
  completion_menu_meta_bg:       "#2e3436"
  completion_menu_meta_current_bg: "#3465a4"

spinner:
  waiting_faces:  [...]              # animated glyphs while waiting for the model
  thinking_faces: [...]              # animated glyphs while the model is thinking
  thinking_verbs: [...]              # verb labels shown with the spinner
  wings: [["⟪", "⟫"], ["[", "]"]]    # bracketing characters around spinner text

branding:                            # the user-visible labels — the part people actually want to change
  agent_name:     "Hermes Agent"
  welcome:        "Welcome to Hermes Agent! ..."
  goodbye:        "Goodbye! <icon>"   # shown on /exit
  response_label: "<icon> Hermes"    # shown next to each assistant reply (this is the one users notice)
  prompt_symbol:  "<icon>"           # shown before the input prompt
  help_header:    "(^_^)? Available Commands"

tool_prefix: "┊"                    # character shown before tool-call lines
```

## Common customizations

**Change the icon next to "Hermes"** — edit `branding.response_label`. Pair it with `branding.goodbye` so they match.

**Change the prompt symbol** — edit `branding.prompt_symbol`.

**Change colors** — edit hex codes under `colors:`. Affects the banner, status bar, completion menu, etc.

**Make the spinner ASCII-only** (e.g. for tmux without UTF-8) — replace the braille `waiting_faces` / `thinking_faces` arrays with simpler characters, e.g. `["|", "/", "-", "\\"]`.

**Use a different skin** — set `skin: <other-name>` in `~/.hermes/config.yaml`.

## Diagnosing "icon shows as a blank box"

Many default skins use **Nerd Font Private Use Area codepoints** for icons — e.g. U+F0F1 is the feather/wing glyph Hermes uses, U+F054 is the chevron prompt, **U+F0238 is `nf-md-fire`** (the flame `terminal-match.yaml` ships with by default). In terminals without a Nerd Font installed, these render as empty tofu boxes (` `) instead of the intended glyph.

To identify which codepoint is in a given field, read the line and decode:

```python
python3 -c "
import re
p = '$HOME/.hermes/skins/terminal-match.yaml'
with open(p, 'rb') as f: data = f.read()
for field in ['response_label', 'goodbye', 'prompt_symbol']:
    m = re.search(rf'{field}:\s*\"([^\"]*)\"'.encode(), data)
    if m:
        s = m.group(1).decode('utf-8')
        cps = ' '.join(f'U+{ord(c):05X}' for c in s if ord(c) > 0x7F)
        print(f'{field:15} {cps}')
"
```

Or one-line with `xxd`:

```bash
sed -n '63p' ~/.hermes/skins/terminal-match.yaml | xxd
```

Output `ef 83 b1` = U+F0F1 (Nerd Font feather). `ef 81 94` = U+F054 (chevron). `f3 b0 88 b8` = U+F0238 (`nf-md-fire`).

**Two fixes** when a glyph shows as tofu:
1. **Install a Nerd Font** in the terminal (JetBrainsMono Nerd Font, FiraCode Nerd Font, etc.) — keeps the intended aesthetic.
2. **Swap the glyph for plain Unicode / ASCII** that renders in the user's terminal, e.g.:
   - `"❯ Hermes"` (bold chevron, plain Unicode)
   - `"› Hermes"` (single chevron)
   - `"[ Hermes]"` (pure ASCII, always renders)

## Verification

After editing, restart Hermes. Skins are loaded at startup — there is no hot-reload.

To confirm a glyph swap landed correctly before restarting:

```bash
# Show the codepoints currently in each branding field
python3 -c "
import re
p = '$HOME/.hermes/skins/terminal-match.yaml'
with open(p, 'rb') as f: data = f.read()
for field in ['response_label', 'goodbye', 'prompt_symbol']:
    m = re.search(rf'{field}:\s*\"([^\"]*)\"'.encode(), data)
    if m:
        s = m.group(1).decode('utf-8')
        cps = ' '.join(f'U+{ord(c):05X}' for c in s if ord(c) > 0x7F)
        print(f'{field:15} {cps}')
"
```

If `response_label` and `goodbye` show the same codepoints, the swap was consistent. If they differ, re-check the source — see pitfalls.

## Pitfalls

- **Edit the active skin, not a copy.** Check `config.yaml` `skin:` first. The bundled `terminal-match.yaml` and `message-text-icon.yaml` are BOTH shipped — only one is active. On this user's setup, the active skin is `terminal-match.yaml` and the rule is to edit it in place rather than forking — small visual tweaks don't deserve a new skin.
- **`response_label` AND `goodbye` reference the SAME icon.** In `terminal-match.yaml` both fields hold the same 4-byte UTF-8 sequence for the chosen glyph. When swapping icons, you must replace BOTH occurrences — otherwise the chat banner and `/exit` message will visually disagree. `grep -c` on the raw bytes is a quick way to confirm both got updated (should be 2 for a paired swap).
- **The `patch` tool can't reliably find raw multi-byte PUA chars in YAML.** Even with exact byte sequences, `patch(mode='replace', old_string="\xf3\xb0\x88\xb8", ...)` may fail with "Could not find a match" because the tool's matching normalizes/escapes differently. For Nerd Font glyph swaps, use terminal Python instead:
  ```python
  path = '$HOME/.hermes/skins/terminal-match.yaml'
  with open(path, 'rb') as f: data = f.read()
  old = '\U000F0238'.encode('utf-8')   # current glyph
  new = '\U000F070B'.encode('utf-8')   # target glyph
  assert data.count(old) >= 1, 'no match — bailing'
  with open(path, 'wb') as f: f.write(data.replace(old, new))
  ```
  Always encode codepoints as `'\UXXXXXXXX'` (8 hex digits, capital) — `'\uXXXX'` only handles BMP (≤ U+FFFF) and breaks on PUA. Add a `data.count(old)` assertion before the write — silent zero-replace bugs are common with PUA chars.
- **High PUA-B codepoints (U+F0700–U+F1FFF) are ambiguous across Nerd Font variants.** The `nf-md-*` set has a canonical mapping at https://github.com/ryanoasis/nerd-fonts/blob/master/glyphnames.json, but codepoints above ~U+F0700 are sparsely documented and different fonts (Material Design vs. custom additions) may render different glyphs at the same codepoint. If the user gives you a bare codepoint in this range (e.g. U+F070B), DO NOT just write it in — ask what icon it should be (rocket, robot, satellite, etc.) or have them confirm the codepoint came from their installed font's glyphnames.
- **Quote hex colors** (`"#8ae234"`, not `#8ae234`). A bare `#` is a YAML comment and the color will silently parse as a string.
- **Don't delete a skin you're using.** Copy it first or create a new file with a different `name:`.
- **Nerd Font codepoints are font-specific.** If you swap skins, the glyph that worked in one terminal may tofu in another — verify after restart.
- **Bundled skins live under `$HERMES_HOME/skins/`, not `~/.hermes/skins/`.** If `~/.hermes/skins/` is empty after a fresh install, the bundled `terminal-match.yaml` / `message-text-icon.yaml` still ship — they're under `$HERMES_HOME/skins/`. On this user's setup HERMES_HOME=/mnt/z/pantheon/.hermes (set by the `hermes` launcher script at `~/.local/bin/hermes`). The user's own config.yaml and custom skins go in `~/.hermes/` as normal; only the *bundled* defaults live in $HERMES_HOME.
- **Translating `nf-md-<name>` to a glyph:** codepoints are in the U+F0001–U+F1AF0 range (Material Design Icons). Construct with `python3 -c "print(chr(0xF0238))"` for `nf-md-fire`. If the glyph renders as a box after restart, the terminal isn't running a Nerd Font — install JetBrainsMono Nerd Font / FiraCode Nerd Font rather than swapping to a fallback codepoint.
