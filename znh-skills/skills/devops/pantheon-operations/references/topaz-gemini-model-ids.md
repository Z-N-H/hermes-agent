# Gemini Model ID Mappings for Nabu / Topaz-Thoth

The Nabu newsroom system hardcodes Gemini model IDs in two files. When Google retires a
model, the entire pipeline crashes with `404 NOT_FOUND`. Keep this file updated.

## Files to patch

1. `nabu/config.py` — `LLM_MODEL_NAME` constant
2. `nabu/api_clients/gemini_client.py` — `get_flash_model()` and `get_pro_model()`

## Current working IDs (verified 2026-06-28)

| Old ID (retired)         | Current Working ID     | Use Case               |
|---------------------------|------------------------|------------------------|
| `gemini-pro-latest`       | `gemini-2.5-pro`       | High-quality writing   |
| `gemini-flash-latest`     | `gemini-2.5-flash`     | Fast checking/summary  |
| `gemini-2.0-flash`        | `gemini-2.5-flash`     | Fallback flash model   |
| `gemini-1.5-pro`          | `gemini-2.5-pro`       | Older pro fallback     |
| `gemini-1.5-flash`        | `gemini-2.5-flash`     | Older flash fallback   |

## How to verify a model ID

```bash
cd /mnt/z/pantheon/projects/topaz-thoth/main
export GOOGLE_API_KEY=<key>
uv run python -c "
from google import genai
client = genai.Client(api_key=os.environ['GOOGLE_API_KEY'])
for m in ['gemini-2.5-pro', 'gemini-2.5-flash']:
    try:
        r = client.models.generate_content(model=m, contents='Hello')
        print(f'{m}: OK — {r.text[:30]}')
    except Exception as e:
        print(f'{m}: FAIL — {str(e)[:80]}')
"
```

## Patching checklist

- [ ] Update `LLM_MODEL_NAME` in `nabu/config.py`
- [ ] Update `get_flash_model()` in `nabu/api_clients/gemini_client.py`
- [ ] Update `get_pro_model()` in `nabu/api_clients/gemini_client.py`
- [ ] Run verification script above
- [ ] Test with a short `uown-blog blog` invocation
