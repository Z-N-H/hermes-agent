# SE Ranking — MCP-gated discovery source (Pantheon hub)

SE Ranking is a **Pantheon MCP** — reached through the orchestrator (or the
orchestrator's `search → get_schema → execute` meta-tool), NOT by leaf
research subagents. It exposes **200+ SEO tools** under namespaces
`seranking_DATA_*` and `seranking_PROJECT_*`.

## When to reach for it in directory research

Confirm the task is real, then use it inside the discovery phase (never to
declare a listing — verification still applies):

1. **Fetch SERPs to harvest candidate URLs.** Run SERP queries for the exact
   category SEO phrases. Example queries per category: "user testing tools",
   "heatmap analytics software", "card sort tool", "session replay software".
   The organic results surface the domains that rank — pull the URLs/domains as
   candidates. A tool ranking for a relevant query is a strong reality check.
2. **Find competitor domains.** Pick a strong, well-known tool already in the
   directory (e.g. usertesting.com, hotjar.com) and run the competitor-domain
   lookup. The overlapping/competing domains are a rich candidate pool in the
   same space.

## Critical pitfall: never guess tool names

SE Ranking tool names under the 200+ namespace are **not guessable**. The
sequence is ALWAYS:

1. **Search the MCP** for the capability (e.g. query "serp", "competitor",
   "domain keywords", "volume") to find the exact tool name. If a search
   returns **0 tools**, the MCP is not mounted — check hub status / re-auth.
2. **`get_schema` the tool before invoking it.** Live parameter names differ
   from what the docs/reference suggest.
3. Then `execute` / invoke.

## Confirmed tool names (reference; re-verify via search each time)

- `seranking_DATA_exportKeywords` — exact-match keyword volume (use lowercase
  short codes like 'uk', 'us').
- `seranking_DATA_getDomainKeywords`
- `seranking_DATA_getRelatedKeywords`
- `seranking_DATA_getSimilarKeywords`
- `seranking_PROJECT_getSearchVolume` — note: returns broad/phrase-match
  volume, HIGHER than the UI; prefer `exportKeywords` for exact-match numbers.
- `seranking_PROJECT_getVolumeRegions` — find other search-volume region codes.
- `seranking_DATA_getDomainCompetitors` — the competitor-domain lookup.

## Invocation detail (Pantheon)

- The Pantheon MCP uses a Code-Mode `execute` meta-tool: pass Python code that
  calls the SE Ranking tool via `call_tool()` **inside the code string**.
- Results are read from `result.content[0].text` as a JSON string (**not**
  `result.data`, which is always None) — parse that text.
- If SE Ranking health shows 'failed'/'connection_error', OAuth is missing or
  expired: run `pantheon mcp auth se-ranking` (flags `--force`, `--check`,
  `--clear`) and restart the gateway.
- If it's unavailable, fall back to plain web search — it's a kit tool, not a
  hard dependency.

## Fallback

Discover via web search + directories (G2, GetApp, Capterra, Product Hunt)
when SE Ranking is down. Never block research on it.
