---
name: web-research-tools
description: How the built-in web_search/web_extract tools resolve providers, where their latency comes from, and how to inspect/tune them — plus the emerald-phoenix deep-scrape stack for pages the built-ins can't fetch.
---

# Web Research Tools — built-in plumbing and beyond

Use this when: web_search/web_extract seem slow, fail, or return poor results; the user asks which search backend/provider is active; you want to tune provider selection; or a page is hard to fetch (403/401, JS-rendered, anti-bot) and built-ins aren't enough.

## Architecture

- `tools/web_tools.py` (in the Hermes source checkout) is a dispatcher. Vendor logic lives in `plugins/web/<vendor>/provider.py`. Providers: tavily, exa, parallel, firecrawl, searxng, brave-free, ddgs (DuckDuckGo, search-only), xai.
- Backend is selected per capability (search vs extract): `web.search_backend` / `web.extract_backend` in config.yaml → `web.backend` → auto-detect from env credentials. Exact priority order and per-provider notes: see `references/provider-resolution.md`.
- `web_extract`: pages under ~5k chars return full markdown; longer pages get an LLM summarization pass via the auxiliary model (config `web_extract` provider/model) capped ~5k chars/page. **That second pass is the main latency source** — extracting two long live blogs takes noticeably longer than the search itself.

## Working with it

- Batch URLs: `web_extract` takes up to 5 URLs in one call — one batched call beats sequential ones.
- Quick factual lookups (scores, dates, headlines): `web_search` snippets often already contain the answer. Weigh whether extract is needed at all, and prefer 1 well-chosen URL over 5. NOTE: the user was offered a snippets-only default for fast answers and explicitly declined — present the speed/depth tradeoff when relevant, but do not impose it as a standing rule.
- Never guess the active backend — check: `grep -A3 '^web:' $HERMES_HOME/config.yaml` and grep provider keys in `$HERMES_HOME/.env` (TAVILY_API_KEY, EXA_API_KEY, etc.).

## Locating the Hermes source

- `echo $HERMES_HOME` first — when set, everything (config, source, venv) lives there, not `~/.hermes`.
- The launcher `~/.local/bin/hermes` is a wrapper that reveals the real install path.
- Source checkout + venv: `$HERMES_HOME/hermes-agent/`. Grep `tools/web_tools.py` for `_get_capability_backend` to see current resolution logic (it evolves — re-check rather than trusting memory of the order).

## When built-ins aren't enough

Built-in extract is plain-HTTP/API-based; anti-bot or JS-heavy pages just fail. emerald-phoenix contains the user's heavier stack (Camoufox anti-detect browser + Crawlee + proxies + trafilatura, with a Tavily fallback) — architecture and paths in `references/emerald-phoenix-scraper-stack.md`. A port as an opt-in `deep_scrape` tool (layered over the built-in path, not replacing it) was discussed 2026-07; confirm with the user before building.

## References

- `references/provider-resolution.md` — exact fallback order, config keys, per-provider notes, dated snapshot of the current setup.
- `references/emerald-phoenix-scraper-stack.md` — paths + architecture of the user's SERP/deep-scrape stack (port candidate).
