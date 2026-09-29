# Dynamic Brand Icon Lookup (`get_active_brand_icon`)

Pattern for making the Hermes CLI dynamically resolve its brand icon from
the active skin instead of hardcoding `⚕` everywhere.

## When to use this

- User has a custom skin with a different icon (e.g. feather ``) but still
  sees the old icon (`⚕`) in status bar, banners, response boxes, or prompts
- You need to make the CLI respect the skin's `branding.response_label`
- You are touching any code that formats `"⚕ Hermes"` or `" ⚕ "` as a literal

## The helper

`hermes_cli/skin_engine.py` now ships `get_active_brand_icon()`:

```python
def get_active_brand_icon(fallback: str = "⚕") -> str:
    """Get the brand icon glyph from the active skin's response_label."""
    try:
        raw = get_active_skin().get_branding("response_label", fallback)
    except Exception:
        raw = fallback
    cleaned = (raw or fallback).strip()
    return cleaned.split(" ", 1)[0] or fallback.strip()
```

It reads the active skin's `response_label` (e.g. `" Hermes"`), extracts
the first word (the icon glyph), and returns it. If the skin engine fails to
load, it returns the fallback.

## Files that had hardcoded `⚕` (2026-06-20 audit)

These are the locations across the CLI where `⚕` was baked in. When you see
a new hardcoded icon, add the file to this list.

| File | Lines | Context |
|------|-------|---------|
| `cli.py` | ~3001 | `_print_banner` default title |
| `cli.py` | ~4176, 4181, 4204 | `_get_status_bar_text` model prefix |
| `cli.py` | ~4224 | `_get_status_bar_text` exception fallback |
| `cli.py` | ~4242, 4259, 4294 | `_get_status_bar_fragments` status prefix |
| `cli.py` | ~4874, 4877 | Response box label (streamed + final) |
| `cli.py` | ~10158 | TTS display callback label |
| `cli.py` | ~10500 | Final response panel label |
| `cli.py` | ~10793 | `_get_prompt_fragments` working indicator |
| `cli_commands_mixin.py` | ~1498 | Background task response label |
| `cli_commands_mixin.py` | ~2216 | Update modal title |
| `cli_commands_mixin.py` | ~2229 | Update launch message |
| `config.py` | ~6014 | Configuration banner |
| `tools_config.py` | ~3401, 3417 | Tool config banners |
| `gateway.py` | ~3876 | Gateway startup banner |
| `gateway.py` | ~5865 | Gateway setup banner |
| `claw.py` | ~351, 577 | OpenClaw migration + cleanup banners |
| `uninstall.py` | ~515, 604 | Uninstaller banners |
| `uninstall.py` | ~882 | Uninstaller goodbye |
| `main.py` | ~2051 | Update relaunch message |
| `main.py` | ~2347 | WhatsApp setup title |
| `main.py` | ~2550 | Setup tips (×2) |
| `main.py` | ~2598 | Post-install bootstrap |
| `main.py` | ~7786 | PyPI update available |
| `main.py` | ~7878 | Git update available |
| `main.py` | ~8428 | Update start message |
| `status.py` | ~99 | Status banner |
| `setup.py` | ~179 | Non-interactive setup title |
| `setup.py` | ~2841 | Nous Portal setup banner |
| `setup.py` | ~2971 | Generic setup banner |
| `setup.py` | ~3007 | Setup wizard banner |
| `setup_whatsapp_cloud.py` | ~241 | WhatsApp Cloud setup title |

## Replacement pattern

For each occurrence, wrap in a lazy import + fallback:

```python
try:
    from hermes_cli.skin_engine import get_active_brand_icon

    _icon = get_active_brand_icon()
except Exception:
    _icon = "⚕"
```

Then use `_icon` in the f-string:

```python
# Banner
print(f"│ {_icon} Hermes Gateway Starting... │")

# Status bar
frags = [("class:status-bar", f" {_icon} "), ...]

# Response label
label = f"{_icon} Hermes"
```

## Do NOT modify built-in skin presets

The user's preference is to **only change the custom skin YAML** and **never
touch `_BUILTIN_SKINS` in `skin_engine.py`**. The built-in `default`, `slate`,
`mono`, `cyberpunk`, `ocean`, `ares`, and `poseidon` presets keep their
original icons. Custom skins in `~/.hermes/skins/*.yaml` override them.

## Pitfall: TUI is already consistent

The Ink/React TUI (`ui-tui/src/theme.ts`) already uses the feather icon
(`\uedf7`). If the user sees the correct icon in the TUI but not the CLI, the
problem is CLI hardcodes — NOT the TUI. Do not waste time rebuilding the TUI.

## Pitfall: skin changes need `/reset` or restart

Skin YAML edits do NOT apply mid-conversation. The skin engine is initialised
once at CLI startup. Tell the user to `/reset` or exit and relaunch after
changing `~/.hermes/skins/*.yaml`.

## Verification

After editing:

```bash
cd hermes-agent
grep -rn '"⚕' hermes_cli/ cli.py  # should show only built-in presets
```

Any remaining `"⚕` outside `_BUILTIN_SKINS` means a file was missed.
