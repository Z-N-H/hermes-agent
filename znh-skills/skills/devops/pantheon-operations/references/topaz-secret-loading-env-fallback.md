# Secret Loading Fallback — Environment Variables

Nabu's `nabu/config.py` fetches API keys exclusively from Google Cloud Secret Manager via
`znh_secrets.access_secret()`. When the gcloud credentials file is missing or unreadable
(e.g. on WSL2 without `gcloud auth application-default login`), all keys return `None` and
the pipeline crashes.

## The fix

Patch `nabu/config.py::_get_secret()` to check environment variables **before** calling
the Secret Manager:

```python
def _get_secret(secret_name: str, secret_id: str):
    """Fetches a secret from the secret manager and caches it. Falls back to env var."""
    if secret_name not in _secrets_cache:
        # First try environment variable
        env_value = os.environ.get(secret_name)
        if env_value:
            logger.info(f"Loaded secret '{secret_name}' from environment variable.")
            _secrets_cache[secret_name] = env_value
            return _secrets_cache[secret_name]
        
        # ... existing GCP Secret Manager fallback ...
```

## Required environment variables

| Secret Name             | Env Var Name          | Purpose                    |
|-------------------------|-----------------------|----------------------------|
| `LLM_API_KEY`           | `LLM_API_KEY`         | Gemini API access          |
| `DATAFORSEO_API_KEY`    | `DATAFORSEO_API_KEY`  | SERP data (DataForSEO)     |
| `HELICONE_API_KEY`      | `HELICONE_API_KEY`    | Helicone proxy/logging     |
| `TAVILY_API_KEY`        | `TAVILY_API_KEY`      | Tavily search (optional)   |
| `SERANKING_API_KEY`     | `SERANKING_API_KEY`   | SE Ranking data (optional) |

## How to check

```bash
cd /mnt/z/pantheon/projects/topaz-thoth/main
uv run python -c "
from nabu.config import get_llm_api_key, get_dataforseo_api_key
print('LLM:', 'OK' if get_llm_api_key() else 'MISSING')
print('DataForSEO:', 'OK' if get_dataforseo_api_key() else 'MISSING')
"
```

If any key shows `MISSING`, set the corresponding env var and retry.
