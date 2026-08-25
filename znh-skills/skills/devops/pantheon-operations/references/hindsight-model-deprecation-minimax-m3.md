# Model Deprecation — MiniMax-M3 (2026-07-29)

## What happened

Hindsight fact extraction silently stopped working. `hindsight_retain` returned 500 with `NotFoundError` on every call. Service health (`/health`) returned 200, so the service was up.

## Root cause

The configured model `hf:MiniMaxAI/MiniMax-M3` was deprecated by the provider. HTTP 404 on every extraction attempt.

## How it was diagnosed

1. `hindsight_retain` → 500, "Fact extraction failed: NotFoundError"
2. Service health check → 200 (service was running)
3. Checked server log: `tail -50 /mnt/z/pantheon/.hermes/logs/hindsight-server.log`
4. Found the real error:
   ```
   WARNING - hindsight_api.engine.providers.openai_compatible_llm - APIStatusError (openai/hf:MiniMaxAI/MiniMax-M3, scope=retain_extract_facts, attempt 1/4): HTTP 404: hf:MiniMaxAI/MiniMax-M3 is no longer supported. Try using a different model, like hf:zai-org/GLM-5.2
   ```

## Key lesson

The 500 error from the API hides the actual cause. The real error (HTTP 404 + provider message about model deprecation) is **only visible in the Hindsight server log**, not in the API response returned to the agent.

## Resolution

Fix not yet applied — user needs to update the Hindsight config to use a working model for `retain_extract_facts`.
