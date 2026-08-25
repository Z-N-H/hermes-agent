# Test Assertion Fix Recipe (Emoji → Nerd Font)

After running `replace_emojis.py`, tests that assert against literal emoji
strings will fail. This reference gives the exact replacements for the
common assertions found in the Hermes Agent test suite.

## Pattern

Read file in UTF-8, do Python `.replace()`, write back. Do NOT use `sed`
— it can mangle Unicode depending on locale.

```python
with open("tests/cli/test_cli_status_bar.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("✓", "\uf00c")  # check → nf-fa-check
content = content.replace("🗜️", "\uf066")  # compression → nf-fa-compress
content = content.replace("⚕", "\uf0f1")  # staff → nf-fa-stethoscope
content = content.replace("🎤", "\uf130")  # microphone → nf-fa-microphone

with open("tests/cli/test_cli_status_bar.py", "w", encoding="utf-8") as f:
    f.write(content)
```

## Hermes-specific assertion table

| Test file | Old emoji | Old assertion | New codepoint | New assertion |
|---|---|---|---|---|
| `tests/agent/test_display_emoji.py` | `⚡` | `assert result == "⚡"` | `\uf0e7` | `assert result == "\uf0e7"` |
| `tests/cli/test_cli_status_bar.py` | `✓` | `assert label == "✓ 42s"` | `\uf00c` | `assert label == "\uf00c 42s"` |
| `tests/cli/test_cli_status_bar.py` | `🗜️` | `assert "🗜️ 3" in text` | `\uf066` | `assert "\uf066 3" in text` |
| `tests/cli/test_cli_status_bar.py` | `⚕` | `assert "⚕" in text` | `\uf0f1` | `assert "\uf0f1" in text` |
| `tests/cli/test_cli_status_bar.py` | `🎤` | `assert "🎤 Ctrl+B" in text` | `\uf130` | `assert "\uf130 Ctrl+B" in text` |
| `tests/cli/test_cprint_bg_thread.py` | `💾` | `assert direct_prints == ["💾 Self-improvement review..."]` | `\uf0c7` | `assert direct_prints == ["\uf0c7 Self-improvement review..."]` |

## Verification command

After fixing assertions:

```bash
pytest tests/agent/test_display_emoji.py tests/cli/test_cli_status_bar.py -v
```

If you see `ModuleNotFoundError: No module named 'httpx'`, that is an
environment issue, not an emoji issue. Install the dependency or skip that
test class.
