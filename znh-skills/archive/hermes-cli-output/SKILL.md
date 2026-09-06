---
name: hermes-cli-output
description: Format responses for Hermes CLI terminal output — rendering tables, data, and structured output without relying on ANSI codes, markdown, or Rich library colors.
version: 1.0.0
platforms: [linux, macos, windows]
environments: [hermes]
---

# Hermes CLI Output Formatting

## How the CLI Renders Responses

Hermes CLI renders responses as **plain text** — no markdown processing, no ANSI escape code passthrough.

**Confirmed rendering behaviour:**
| Feature | Works? | Notes |
|---------|--------|-------|
| ANSI escape codes (`\e[32m`) | ❌ | Stripped from both `terminal()` tool output and inline response text |
| Markdown tables | ❌ | Render as literal dashes and pipes — no table formatting |
| Rich library ANSI output | ❌ | Colours don't survive the transport pipeline |
| Unicode box-drawing chars | ✅ | `┌ ─ ┐ │ └ ┘ ├ ┤ ┬ ┴` render cleanly |
| Plain text with spacing | ✅ | Spaces, newlines, and alignment all preserved |

## Table Formatting

For any tabular data, construct tables using Unicode box-drawing characters directly in your response text:

```
┌──────────────────────┬──────────┐
│ Metric               │ Value    │
├──────────────────────┼──────────┤
│ Monthly Volume       │ 49,500   │
│ Keyword Difficulty   │ 90 / 100 │
│ CPC                  │ £0.00    │
└──────────────────────┴──────────┘
```

**Characters to use (copy-paste friendly):**
- Top corners: `┌ ─ ┐` 
- Bottom corners: `└ ─ ┘`
- Row separators: `├ ─ ┤`
- Column separators: `│`

**Formatting rules:**
- Pad column content with spaces to equal width
- Use `───` (triple em-dash) or `──` (double em-dash) for horizontal borders
- Column headers in plain text (no bold, no colour — neither survive)
- Left-align text, right-align numbers

## When to Use

- Any response containing tabular data (search results, metrics, comparisons, lists, volumes)
- SEO data from SE Ranking or other tools
- Configuration comparisons, before/after, side-by-side values
- Any structured data the user needs to scan quickly

## What NOT to Do

- ❌ Do NOT use Rich library for ANSI-coloured output in responses — colours don't survive
- ❌ Do NOT use markdown tables — they render as literal plain text with pipes
- ❌ Do NOT dump raw Python dicts or JSON — format as a table
- ❌ Do NOT rely on `terminal()` tool's stdout for formatting — ANSI codes are stripped in capture
- ❌ Do NOT use ANSI bold/colour in inline response text — the escape sequences are not passed through

## Pitfalls

- **Testing ANSI passthrough:** Running `echo -e "\e[32mtest\e[0m"` via the terminal tool returns just `test` — confirm before relying on ANSI in any channel.
- **Markdown deception:** Markdown tables look correct in your response text when you're writing it, but the Hermes CLI does not process markdown — the user sees raw `| Metric | Value |` text.
- **Rich library in terminal() calls:** Even with `force_terminal=True` and `color_system='truecolor'`, Rich output captured through the terminal tool loses all ANSI codes. The box-drawing skeleton survives; the styling does not.

## Related Skills

- `using-se-ranking-mcp` — SEO data queries; use this skill's table format when presenting results
