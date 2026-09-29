# Hermes Branding Icon Locations

When replacing the Hermes brand icon (e.g. stethoscope ⚕ → feather ) or the
assistant response icon (e.g. fire 󰈸), both the **TUI** and the **CLI** must be
updated. They do not share a single source of truth.

## TUI (Ink/React terminal UI)

The TUI uses **hardcoded TypeScript defaults** in `ui-tui/src/theme.ts`. Skin
YAML files are **NOT** read by the TUI branding system.

Key files:

- `ui-tui/src/theme.ts` — `BRAND.icon`, `BRAND.goodbye`
- `ui-tui/src/components/appLayout.tsx` — no-session status prefix (`⚕ {status}`)
- `ui-tui/src/components/appChrome.tsx` — `EMOJI_FRAMES[0]` (busy spinner glyph)
- `ui-tui/src/components/branding.tsx` — banner rendering (reads `t.brand.icon`)

The TUI already ships with `icon: '\uedf7'` (fa-feather) in `theme.ts`. If the
user sees the correct icon in the TUI, **do not** rebuild it — the problem is
the CLI, not the TUI.

Steps (only if the TUI icon is wrong):
1. Edit `theme.ts` `BRAND.icon` and `BRAND.goodbye`.
2. Edit `appLayout.tsx` hardcoded status prefix.
3. Edit `appChrome.tsx` `EMOJI_FRAMES` array entry 0.
4. Run `npm run build` in `ui-tui/` to rebuild `dist/entry.js`.

## CLI (Rich console output)

The CLI reads **skin YAML** or built-in Python presets from `skin_engine.py`.
However, `⚕` was hardcoded in dozens of places across `cli.py`, `hermes_cli/*.py`,
etc., bypassing the skin system entirely. The correct fix is to use the
`get_active_brand_icon()` helper (see `references/dynamic-brand-icon-lookup.md`)
rather than editing each file's literal string.

Key files:

- `hermes_cli/skin_engine.py` — built-in skin presets (`branding.response_label`)
  + `get_active_brand_icon()` helper
- `~/.hermes/skins/*.yaml` — active user skin overrides (check `config.yaml` `display.skin`)
- `cli.py` + `hermes_cli/*.py` — hardcoded `⚕` fallbacks that must be switched to
  `get_active_brand_icon()`

Steps:
1. Check `config.yaml` for the active skin name (`display.skin`).
2. Edit that skin YAML (`~/.hermes/skins/<skin>.yaml`) `branding.response_label`
   and `branding.goodbye`.
3. **Do NOT modify built-in presets** in `skin_engine.py` `_BUILTIN_SKINS`.
4. Replace every hardcoded `⚕` in `cli.py` and `hermes_cli/*.py` with
   `get_active_brand_icon()` using the lazy-import pattern.
5. See `references/dynamic-brand-icon-lookup.md` for the full file list and
   replacement recipe.

## NerdFont lookup

Hermes ships `data/nerdfonts/glyphnames.json`. Use it to verify a glyph name and
its Unicode codepoint before hardcoding:

```python
import json

data = json.load(open("data/nerdfonts/glyphnames.json"))
# info = {'char': '\ueef7', 'code': 'eef7'}
name = "fa-feather"  # NerdFont glyph name
info = data[name]
print(f"U+{info['code'].upper()}  {info['char']}")
```

Pitfall: some icons in the default skin are **Material Design** glyphs (e.g.
`md-fire` U+F0238) rather than NerdFont (`nf-*`). If replacing, pick a NerdFont
glyph that renders in the user's terminal font.

## Verification

- TUI: `npm run typecheck` and `npm run build` in `ui-tui/` (only if TUI changed).
- Python icon registry: `python3 -m pytest tests/test_hermes_icons.py`.
- Restart Hermes (`/reset` or relaunch) to pick up rebuilt TUI bundles and CLI
  skin changes. Skin engine is initialised once at startup.
