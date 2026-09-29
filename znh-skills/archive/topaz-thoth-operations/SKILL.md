---
name: topaz-thoth-operations
description: "Operate the topaz-thoth (Nabu newsroom) blog generation system — run article workflows, troubleshoot model deprecation, fix secret loading, and handle WSL2 multiprocessing issues."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [topaz-thoth, nabu, blog-generation, content-generation, uown-blog, pantheon]
---

# Topaz-Thoth Operations

## Overview

Topaz-thoth is a Pantheon-registered project (also called "Nabu newsroom") that generates
SEO-optimised blog articles via a multi-agent critique loop. It lives in the Pantheon
projects tree and is invoked through a Typer CLI (`uown-blog`).

## When to Use

- User says "use topaz-thoth", "use nabu", "use uown-blog", or "generate an alternatives article"
- Generating blog posts, comparison roundups, or SEO content for a client
- Troubleshooting the blog generation pipeline after model API changes
- Setting up or verifying a client's brand soul

## Project Location

The Pantheon `registry.json` claims `live_local: /mnt/z/nabu`, but that path is often
inaccessible. The real project is at:

```
/mnt/z/pantheon/projects/topaz-thoth/main/
```

Always `cd` there before running commands.

## CLI Reference

The entry point is `uv run uown-blog` (the project uses `uv`, never bare `python`).

### Generate a single article

```bash
cd /mnt/z/pantheon/projects/topaz-thoth/main
uv run uown-blog blog "<topic>" \
  --locale <us|uk|au|ca> \
  --client <client_id> \
  --article-type <ALTERNATIVES|...> \
  --notes "<context for research and writing>"
```

**Example:**
```bash
uv run uown-blog blog "Achievers alternatives" \
  --locale us \
  --client thankbox \
  --article-type ALTERNATIVES \
  --notes "Focus on the Achievers employee recognition platform. Target US HR managers."
```

Output is saved to `storage/<client>/output/posts/<timestamp>_<slug>.md`.

### Attach a Google Sheet for batch generation

```bash
uv run uown-blog sheets attach <client_id> \
  --sheet-id <sheet_id> \
  --drive-folder <drive_folder_id>
```

### Poll a sheet and auto-generate rows

```bash
uv run uown-blog sheets run <client_id> --interval 60
```

### List available clients (brand souls)

Clients are directories under `storage/`. Each must contain `brand_soul.toml`.

```bash
ls /mnt/z/pantheon/projects/topaz-thoth/main/storage/
```

## Brand Souls

Brand souls live in `storage/<client_id>/brand_soul.toml`. They define voice, audience,
steering logic, and vibe checks. The `create_client.py` script bootstraps a new client
from a TOML in `brand_souls/`.

**To add a new client:**
1. Write a `brand_soul.toml` in `brand_souls/<client_id>.toml`
2. Run `uv run python create_client.py` and select it from the list
3. Verify: `ls storage/<client_id>/`

## Article Types

The `--article-type` flag switches prompt templates in `nabu/prompts/`:

- `ALTERNATIVES` — "alternatives to X" roundups with fixed H2/H3 structure
- Omit for default behaviour (general long-form)

## Known Issues & Maintenance

### 1. Gemini model names deprecate without warning

`nabu/config.py` sets `LLM_MODEL_NAME` and `nabu/api_clients/gemini_client.py` hardcodes
`gemini-pro-latest` / `gemini-flash-latest`. Google retires these periodically, causing:

```
google.genai.errors.ClientError: 404 NOT_FOUND
This model models/gemini-2.0-flash is no longer available.
```

**Fix:** Update both files to current model IDs. As of 2026-06-28 the working IDs are:
- `gemini-2.5-pro` (replaces `gemini-pro-latest`)
- `gemini-2.5-flash` (replaces `gemini-flash-latest`)

See `references/gemini-model-ids.md` for the full mapping.

### 2. Secret loading only uses Google Cloud Secret Manager

`nabu/config.py::_get_secret()` calls `access_secret()` from `znh_secrets.py`, which talks
to GCP Secret Manager. If the gcloud credentials file is missing or unreadable, all API
keys return `None` and the pipeline crashes.

**Fix:** Patch `_get_secret()` to check environment variables first:

```python
def _get_secret(secret_name: str, secret_id: str):
    if secret_name not in _secrets_cache:
        env_value = os.environ.get(secret_name)
        if env_value:
            _secrets_cache[secret_name] = env_value
            return _secrets_cache[secret_name]
        # ... rest of GCP fallback
```

Required env vars: `LLM_API_KEY`, `DATAFORSEO_API_KEY`, `HELICONE_API_KEY`.

### 3. WSL2 multiprocessing breaks crawlee/scrapers

Crawlee (used for SERP content scraping and Reddit context) spawns Playwright processes
via `multiprocessing`. On WSL2 this fails with `[Errno 13] Permission denied` on semaphores,
producing `Scraped 0 pages` and empty intelligence reports.

The pipeline can still complete using model knowledge and SERP snippets, but depth suffers.
See the `wsl-environment` skill for the full semaphore fix.

### 4. DataForSEO SERP API is optional

If `DATAFORSEO_API_KEY` is unavailable, the intelligence layer falls back to Tavily (if
configured) or pure model knowledge. The article quality degrades slightly but remains
usable.

## Workflow Overview

1. **Research Phase** — community context (Reddit), fan-out plan, intelligence layer (SERP facts)
2. **Outline Phase** — outline strategist generates a structured `ArticleOutline`
3. **Draft Phase** — writer agent produces the initial draft
4. **Review Loop** — three critics (Fact-Checker, Style Linter, Editor) review in parallel,
   up to 5 iterations
5. **Final Polish** — brand voice agent applies editorial gloss
6. **Output** — markdown saved to client output directory

## Quick Verification

```bash
cd /mnt/z/pantheon/projects/topaz-thoth/main
uv run python -c "from nabu.config import get_llm_api_key; print('LLM key:', 'OK' if get_llm_api_key() else 'MISSING')"
uv run python -c "from nabu.brand_souls import list_brand_souls; print(list_brand_souls())"
```