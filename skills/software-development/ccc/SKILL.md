---
name: ccc
description: "Use for ANY local file/codebase search — finding code, files, references, symbols, 'where is X', 'which files use Y'. ccc search is the mandatory first tool call, ahead of search_files/grep/find, for every such query."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [search, codebase, ccc, cocoindex, grep, semantic-search]
    related_skills: [systematic-debugging, plan]
prerequisites:
  commands: [ccc]
---

# ccc — Semantic Code Search

## Overview

`ccc` (CocoIndex Code) is a semantic-vector search CLI over the current codebase. It finds conceptually related code, not just exact string matches — "where is auth handled", "database connection pooling", "which files use the retry decorator" — the kind of query that turns into a wall of grep hits and manual triage. It also handles what grep handles (names, literal strings) just as well, so there is no query class where reaching for `search_files`/grep/find first is the right call.

`search_files` (the built-in tool) is ripgrep-backed. Its own description says "use this instead of grep/rg/find/ls in terminal" — that line is about replacing *shell* grep, not about outranking `ccc`. Don't read tool-list convenience as a signal to skip `ccc`.

## HARD RULE: ccc FIRST, ALWAYS, FOR ANY LOCAL FILE SEARCH

**The very first tool call for ANY local file or codebase search MUST be `ccc search` via the `terminal` tool.** This covers: finding where something is defined, locating a file, checking what code uses a symbol/library/pattern, searching for an error string, listing files matching a name — every case where you'd otherwise reach for `search_files`, shell `grep`/`rg`/`ag`/`find`, or `ls`.

**NEVER** call `search_files` or shell out to `grep`/`rg`/`ag`/`find` as the FIRST search action for a local-search query, regardless of whether the query is conceptual or a literal string/filename. `ccc search` handles literal terms fine — try it before assuming you need ripgrep.

**Exception (rare) — fall back to `search_files`/grep only when ALL of these are true:**
1. `ccc search` returned nothing useful, AND
2. The query is purely lexical (exact string/regex, a specific known variable/identifier), AND
3. Retrying with `ccc search --path 'subtree/*'` narrowed to the likely location didn't help either.

**If you catch yourself reaching for `search_files` or `terminal grep`/`find` without having tried `ccc search` first: stop, use `ccc search`.**

## Running a Search

```bash
ccc search <natural language query>
```

Examples:

```bash
ccc search database connection pooling
ccc search user authentication flow
ccc search error handling retry logic
ccc search where is the search_files tool registered
```

Query with the concept/behavior you're looking for, not exact code syntax.

### Filtering

```bash
ccc search --lang python --lang markdown database schema     # restrict by language, repeatable
ccc search --path 'src/api/*' request validation             # restrict by path glob (default: cwd)
ccc search --offset 5 --limit 5 database schema              # pagination
```

If results look relevant but incomplete, page with `--offset` before giving up.

### Reading results

Results include file paths and line ranges. Load the matched file with `read_file` (offset/limit around the returned range) to get full context — don't rely on the snippet alone for anything you're about to edit.

## Setup / Troubleshooting

`ccc` is expected to already be on PATH (installed via `uv tool install --upgrade 'cocoindex-code[full]'`). Own the lifecycle yourself — don't ask the user to run these steps:

- **`ccc search` fails with "Not in an initialized project directory"** → run `ccc init` from the project root, then `ccc index`, then retry.
- **Index may be stale** (new files, big refactor, start of session) → run `ccc index` (or `ccc search --refresh`) before relying on results. No need to re-index between consecutive searches with no code changes in between.
- **`ccc: command not found`** → `uv tool install --upgrade 'cocoindex-code[full]'`, then retry.
- **Something looks systemically wrong** (daemon stuck, embeddings failing) → `ccc doctor` for end-to-end diagnostics; `ccc daemon restart` to recover a stuck daemon.

## Common Pitfalls

1. **Defaulting to `search_files` because it's already in the tool list and looks "good enough."** It being present and well-described is not permission to skip `ccc`. `ccc search` is the first call, full stop, for every local-search query — including ones that look like simple grep jobs.
2. **Treating literal/filename searches as exempt.** `ccc search` handles exact terms and file-name-shaped queries too; the exception carve-out is narrow (all three conditions must hold), not "literal string, so grep is fine."
3. **Phrasing queries like grep patterns.** `ccc search UserAuth\|auth_user\|AuthManager` defeats the point — write `ccc search user authentication logic` instead and let semantic search handle naming variance.
4. **Not re-indexing after a big refactor.** Stale index returns confidently wrong (missing/renamed) results. Run `ccc index` if the codebase changed materially since last search.
5. **Treating a snippet as ground truth.** Always open the file at the returned line range before editing — snippets can lack surrounding context (imports, class scope, decorators).

## Verification Checklist

- [ ] `ccc search` was the first tool call for this local-search query — no `search_files`/grep/find attempted before it
- [ ] If falling back to `search_files`/grep, all three exception conditions were actually met (not just "felt lexical")
- [ ] If results were empty/stale, ran `ccc index` and retried before falling back to grep
