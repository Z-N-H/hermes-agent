---
name: hindsight-operations
description: Diagnose and fix Hindsight memory service issues — retain/recall failures, fact extraction errors, service health, and model deprecation. Use when hindsight_retain or hindsight_recall fails, or when debugging Hindsight service behavior.
version: 1.0.0
platforms: [linux]
environments: [hermes]
metadata:
  hermes:
    tags: [hindsight, memory, operations, troubleshooting]
    related_skills: [cron-operations]
---

# Hindsight Operations

## Service Health Check (First Diagnostic Step)

When Hindsight operations fail, check service health first:

```bash
# Check systemd status
systemctl --user status pantheon-hindsight.service

# Check API health endpoint
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8888/health
```

Expected: `active (running)` + HTTP 200.

If service is down or health check fails, restart:
```bash
systemctl --user restart pantheon-hindsight.service
```

## Fact Extraction Failures

### Symptom
`hindsight_retain` returns:
```
Failed to store memory: (500)
{"detail": "Fact extraction failed: 1/1 chunks failed. First failures: chunk 0: NotFoundError"}
```

### Root Cause
The LLM model configured for Hindsight's `retain_extract_facts` scope is no longer available at the provider. The API returns HTTP 404, which gets wrapped into a generic `NotFoundError` inside Hindsight's fact extraction pipeline. The 500 response from the API hides the actual cause.

### Diagnosis
**The real error is only in the Hindsight server log:**
```bash
tail -50 /mnt/z/pantheon/.hermes/logs/hindsight-server.log
```

Look for lines like:
```
WARNING - hindsight_api.engine.providers.openai_compatible_llm - APIStatusError (openai/hf:MiniMaxAI/MiniMax-M3, scope=retain_extract_facts, attempt 1/4): HTTP 404: hf:MiniMaxAI/MiniMax-M3 is no longer supported. Try using a different model, like hf:zai-org/GLM-5.2
```

The `scope=retain_extract_facts` identifies which operation is affected. The model name and HTTP status reveal the deprecation.

### Fix
Update the Hindsight config to use an available model for fact extraction. The exact config location depends on how Hindsight is configured — check `.hermes/` for Hindsight config files. After changing the model, restart the service:
```bash
systemctl --user restart pantheon-hindsight.service
```

See `references/model-deprecation-minimax-m3.md` for the full diagnosis of the MiniMax-M3 deprecation event.

## Recall Failures

When `hindsight_recall` fails, check:
1. Is the service running? (health check above)
2. Is the database healthy? Check server log for PostgreSQL errors.
3. Is the bank name correct? Default is `hermes`.

## Common Pitfalls

### 1. API 500 does not mean the service is down
The `/health` endpoint may return 200 while fact extraction fails. The service can be fully operational (DB connected, API responding) but unable to extract facts due to LLM model issues. **Always check the server log, not just the health endpoint.**

### 2. Model deprecation is silent until it strikes
Hindsight won't warn ahead of time when a configured model is being deprecated by the provider. Retain calls just start failing. If recall still works (it uses vector search, not LLM extraction), the service is partially functional but unable to store new memories.

### 3. Fact extraction uses a different model than your session
Hindsight's fact extraction pipeline has its own model configuration, separate from the model you're chatting with. Changing your chat model does not fix a broken extraction model.
