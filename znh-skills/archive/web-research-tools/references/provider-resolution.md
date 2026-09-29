# Provider resolution for web_search / web_extract

Verified against `tools/web_tools.py` on 2026-07-22. The logic evolves — re-check `_get_capability_backend` in the source before relying on this.

## Order of authority (per capability: search, extract)

1. `web.search_backend` / `web.extract_backend` in `$HERMES_HOME/config.yaml` — explicit per-capability override. Honored even if unrecognized/typo'd (dispatcher surfaces that backend's own error rather than silently rerouting).
2. `web.backend` — shared fallback.
3. Auto-detect from environment, in this priority order:

| # | Backend | Availability check | Search | Extract |
|---|---------|-------------------|--------|---------|
| 1 | tavily | `TAVILY_API_KEY` | yes | yes |
| 2 | exa | `EXA_API_KEY` | yes | yes |
| 3 | parallel | `PARALLEL_API_KEY` | yes | yes |
| 4 | firecrawl | `FIRECRAWL_API_KEY` or `FIRECRAWL_API_URL` | yes | yes |
| 5 | firecrawl | managed tool gateway ready (Nous OAuth) | yes | yes |
| 6 | searxng | `SEARXNG_URL` | yes | yes |
| 7 | brave-free | `BRAVE_SEARCH_API_KEY` | yes | — |
| 8 | parallel | keyless free MCP — always available (no-key default) | yes | yes |
| 9 | ddgs | `ddgs` package importable | yes | — |

Search-only backends are skipped when resolving extract.

## Per-provider notes

- **tavily** — search + extract. Extract = POST `https://api.tavily.com/extract`, returns clean markdown (do NOT re-run HTML parsers on it).
- **exa / parallel / firecrawl** — full search+extract vendors; exa and tavily clients are sync, parallel/firecrawl async.
- **searxng** — self-hosted metasearch, needs `SEARXNG_URL`.
- **brave-free** — Brave search only.
- **ddgs** — DuckDuckGo, search only, last resort.
- **xai** — search via xAI credentials.

## Extract summarization pass

`web_extract` fetches via the resolved extract backend, then for pages over ~5k chars runs an LLM summary via the auxiliary model (config section `web_extract:` with `provider`, `model`, `base_url`) and caps output ~5k chars/page. This second pass is why multi-URL extracts of long pages (live blogs, docs) feel slow. Mixing providers is supported, e.g. searxng for search + firecrawl for extract.

## Snapshot of this setup (2026-07-22, re-verify before relying)

- `config.yaml`: `web.backend`, `web.search_backend`, `web.extract_backend` all empty → auto-detect.
- `.env`: only `TAVILY_API_KEY` present → both tools resolve to **tavily**.

## How to verify live

```bash
grep -A3 '^web:' $HERMES_HOME/config.yaml
grep -oE '^(TAVILY|EXA|PARALLEL|FIRECRAWL|SEARXNG|BRAVE)[A-Z_]*' $HERMES_HOME/.env
```
