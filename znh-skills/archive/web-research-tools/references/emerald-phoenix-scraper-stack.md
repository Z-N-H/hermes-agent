# emerald-phoenix search/scrape stack

Inventory taken 2026-07-22 for a potential port to a Hermes-usable tool. Source: `/mnt/z/pantheon/projects/emerald-phoenix/main/` — this is a **production symlink, read-only**. If porting, lift the modules into their own home; do not import across from `main/`.

## Searcher — `nabu/api_clients/serp_retrieval.py`

- DataForSEO Google Organic Live Advanced API: POST `https://api.dataforseo.com/v3/serp/google/organic/live/advanced`.
- Auth: Basic, base64 of the `login:password` credential string from `config.get_dataforseo_api_key()`.
- Region-aware via location_code map: us 2840, uk 2826, au 2036, ca 2124 (extensible; unsupported region currently returns None rather than falling back).
- Returns organic results + People-Also-Ask questions (`people_also_ask_click_depth: 1`, costs extra).
- Paid per query; retries with backoff on network/5xx.

## Scraper — `nabu/core/scrapers.py` + `nabu/services/content_scraper.py`

- Crawlee `PlaywrightCrawler` with a custom `CamoufoxPlugin`: Camoufox (anti-detect Firefox fork) via `AsyncNewBrowser` — OS fingerprint randomization across windows/macos/linux, `humanize=2.0`, `geoip=True` (matches geolocation to proxy IP), `block_webrtc=True`, `disable_coop=True`.
- Proxy rotation from `config.get_proxy_urls()`; 5 request retries; concurrency 25.
- Waits for `load` then best-effort `networkidle` (15s timeout, proceeds anyway).
- Extraction: trafilatura with `MIN_EXTRACTED_SIZE=500`, `MIN_OUTPUT_SIZE=250`; keeps raw HTML + clean text in a `ScrapedContent` model.
- Optional crawl depth: only enqueues links from depth-0 pages (homepage), filtered to same domain, excluding binaries/mailto/tel.
- **Fallback chain**: on 401/403 (Crawlee raises SessionError before the handler, intercepted in `_failed_request_handler`) → `nabu/api_clients/tavily_client.py` `fetch_tavily_content(url)` (Tavily Extract → markdown, already clean, never re-run trafilatura on it).
- `ContentScraper` service = depth-0 batch wrapper over `CoreScraper`.

## Known limits

- Hit permission errors on Reddit threads and some competitor pages (2026-06) despite the anti-detect stack — not bulletproof.
- Heavy per invocation: spins up a real browser, proxy setup, networkidle waits. Wrong tool for quick single-page fetches.

## Port discussion (2026-07-22, decision pending with user)

- Recommendation given: port as a **specialist fallback** (`deep_scrape` tool), layered over the built-in Tavily-backed path — not a replacement. The valuable half is the scraper; the DataForSEO searcher is a maybe (region-targeted SERPs + PAA are the standout, useful for SEO work).
- Per user conventions it should live behind the Pantheon MCP hub or as a Hermes plugin; keys from env/config only, never exposed.
- Amusing overlap: the built-in `web_extract` already resolves to Tavily — i.e. the built-in path IS this stack's plan B. Porting adds the plan-A primary path on top.
