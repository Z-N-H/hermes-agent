# NerdFontIcons API Reference

Lazy lookup class for Nerd Font icons, backed by `data/nerdfonts/glyphnames.json`
(v3.4.0, 10,765 entries). Thread-safe, parses once on first access.

## Module: `hermes_icons`

```python
from hermes_icons import NerdFontIcons, ICON_OK, ICON_WARN
```

### `NerdFontIcons.get(key: str, default: str = "") -> str`

Lookup by full key. Returns the actual Unicode character (not an escape
sequence).

```python
NerdFontIcons.get("fa-check")  # -> "\uf00c"
NerdFontIcons.get("fa-circle_check")  # -> "\uf05d"
NerdFontIcons.get("md-robot")  # -> "\U000f06a9"
NerdFontIcons.get("nonexistent")  # -> "" (default)
NerdFontIcons.get("nonexistent", "?")  # -> "?"
```

### `NerdFontIcons.get_by_emoji(emoji: str, default: str = "") -> str`

Reverse lookup: emoji character → Nerd Font codepoint. Handles variation
selector-16 (`\ufe0f`) transparently.

```python
NerdFontIcons.get_by_emoji("✅")  # -> "\uf05d"
NerdFontIcons.get_by_emoji("⚠️")  # -> "\uf071"  (with VS16)
NerdFontIcons.get_by_emoji("⚠")  # -> "\uf071"  (without VS16)
NerdFontIcons.get_by_emoji("🚀")  # -> "\uf135"
NerdFontIcons.get_by_emoji("🤖")  # -> "\U000f06a9"
```

This is the replacement engine used by `replace_emojis.py`.

### `NerdFontIcons.find(query: str) -> list[str]`

Fuzzy substring search across all keys (case-insensitive).

```python
NerdFontIcons.find("check")  # -> ['cod-check', 'fa-check', ...]
NerdFontIcons.find("robot")  # -> ['md-robot', 'md-robot-angry', ...]
```

### `NerdFontIcons.keys() -> list[str]`

All available full keys (excludes the upstream `METADATA` block).

```python
len(NerdFontIcons.keys())  # -> 10765 (v3.4.0)
```

### `NerdFontIcons._reset()`

Clear cached lookup tables. **For tests only.**

```python
# In a test fixture
NerdFontIcons._reset()
```

## Back-compat aliases

Existing code using `from hermes_icons import ICON_OK` keeps working. All
aliases are defined via `NerdFontIcons.get()` and produce byte-identical values:

| Alias | Key | Value |
|-------|-----|-------|
| `ICON_BRAND` | `fa-stethoscope` | `\uf0f1` |
| `ICON_PROMPT` | `fa-chevron_right` | `\uf054` |
| `ICON_OK` | `fa-check` | `\uf00c` |
| `ICON_OK_CIRCLE` | `fa-circle_check` | `\uf05d` |
| `ICON_FAIL` | `fa-xmark` | `\uf00d` |
| `ICON_FAIL_CIRCLE` | `fa-circle_xmark` | `\uf05c` |
| `ICON_WARN` | `fa-triangle_exclamation` | `\uf071` |
| `ICON_BAN` | `fa-ban` | `\uf05e` |
| `ICON_BOLT` | `fa-bolt` | `\uf0e7` |
| `ICON_GEAR` | `fa-gear` | `\uf013` |
| `ICON_COMPRESS` | `fa-compress` | `\uf066` |
| `ICON_ROTATE` | `fa-arrows_rotate` | `\uf021` |
| `ICON_EYE` | `fa-eye` | `\uf06e` |
| `ICON_MAGNIFY` | `fa-magnifying_glass` | `\uf002` |
| `ICON_FLOPPY` | `fa-floppy_disk` | `\uf0c7` |
| `ICON_PHONE` | `fa-phone` | `\uf095` |
| `ICON_COMMENT` | `fa-comment` | `\uf075` |
| `ICON_ROBOT` | `md-robot` | `\U000f06a9` |
| `ICON_WRENCH` | `fa-screwdriver_wrench` | `\uef70` |
| `ICON_GLOBE` | `fa-globe` | `\uf0ac` |
| `ICON_ROCKET` | `fa-rocket` | `\uf135` |
| `ICON_CHART` | `fa-chart_bar` | `\uf080` |
| `ICON_LIST` | `fa-clipboard_list` | `\ued7b` |
| `ICON_NOTE` | `fa-note_sticky` | `\uf249` |
| `ICON_BOX` | `fa-box` | `\ued75` |
| `ICON_FOLDER` | `fa-folder` | `\uf07b` |
| `ICON_DICE` | `fa-dice` | `\uedec` |

All aliases are also aggregated in the `ICON_NAMES: dict[str, str]` dict.

## Data file

`data/nerdfonts/glyphnames.json` — the upstream Nerd Fonts v3.4.0 metadata,
pinned in the repo. Update explicitly on new Nerd Fonts releases:

```bash
curl -sL https://raw.githubusercontent.com/ryanoasis/nerd-fonts/master/glyphnames.json \
  -o data/nerdfonts/glyphnames.json
```
