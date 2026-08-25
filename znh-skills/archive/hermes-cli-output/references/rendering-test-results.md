# Hermes CLI Rendering Test Results (2026-07-24)

## Test: ANSI escape codes in response text

Sent raw ANSI codes directly in response: `\x1b[32mGREEN\x1b[0m \x1b[31mRED\x1b[0m`

**Result:** ❌ User confirmed "no" — no colour rendered. ANSI codes stripped or not passed through in Hermes CLI.

## Test: ANSI escape codes via terminal tool

Ran `echo -e "\e[32mGREEN\e[0m \e[31mRED\e[0m"` through the terminal tool.

**Result:** ❌ Output returned as literal `GREEN RED` — ANSI codes stripped in capture.

## Test: Markdown table

Sent a standard markdown table to user: `| Metric | Value |` with header separators.

**Result:** ❌ User confirmed "nope, all dashes" — markdown not processed, rendered as raw pipes and dashes.

## Test: Rich library with force_terminal=True

```python
console = Console(force_terminal=True, color_system='truecolor')
table = Table(box=box.ROUNDED, border_style='cyan')
console.print(Panel(table, border_style='cyan'))
```

Ran via `uv run` through the terminal tool with `2>&1 | tail -15`.

**Result:** ⚠️ Partial — box-drawing characters (`╭ ╮ ╰ ╯ │ ┤ ├`) rendered but ANSI colour codes stripped. User said "It just looks like a white table in hermes to me."

## Test: Unicode box-drawing table (manually formatted)

Sent a hand-formatted table using `┌ ─ ┐ │ └ ┘ ├ ┤ ┬ ┴` characters.

**Result:** ✅ User confirmed "yes" — clean rendering.

## Conclusion

For Hermes CLI output:
- Use Unicode box-drawing characters for tables
- Strip all ANSI codes from output (they don't survive)
- Don't use markdown (not processed)
- Plain text with spacing and box-drawing chars is the only reliable rendering path
