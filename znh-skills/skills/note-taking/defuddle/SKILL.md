---
name: defuddle
description: Use when extracting clean markdown content from web pages using the Defuddle CLI — for articles, blog posts, documentation, or any standard web page URL. Use instead of WebFetch to save tokens by removing navigation, ads, and clutter. Do NOT use for URLs ending in .md (already markdown, use WebFetch directly).
---

# Defuddle

Use Defuddle CLI to extract clean readable content from web pages. Prefer over WebFetch for standard web pages — it removes navigation, ads, and clutter, reducing token usage.

## Installation
If not installed:
```bash
npm install -g defuddle
```

## Usage
Always use `--md` for markdown output:
```bash
defuddle parse <url> --md
```

Save to file:
```bash
defuddle parse <url> --md -o content.md
```

Extract specific metadata:
```bash
defuddle parse <url> -p title
defuddle parse <url> -p description
defuddle parse <url> -p domain
```

## Output Formats
| Flag | Format |
|------|--------|
| `--md` | Markdown (default choice) |
| `--json` | JSON with both HTML and markdown |
| (none) | HTML |
| `-p <property>` | Specific metadata property |

## Common Pitfalls
- Requires Node.js and npm to be installed
- The `--md` flag is strongly recommended for LLM consumption — raw HTML is much larger
- Does not work with `.md` URLs (those are already markdown)