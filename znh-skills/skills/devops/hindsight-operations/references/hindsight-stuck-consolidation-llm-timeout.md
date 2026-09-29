# Hindsight Stuck Consolidation / LLM Timeout (2026-08-16)

## Symptom

The UI loads but "isn't working properly" — memory operations that need an LLM
call (consolidation, summarization) hang or stall instead of returning.

- `systemctl --user status pantheon-hindsight.service` → `active (running)`
- `curl http://127.0.0.1:8888/health` → `{"status":"healthy","database":"connected"}`
- Tailnet UI reachable: `curl https://bazzite.centaur-perch.ts.net/` → HTTP 307
  (Next.js control-plane root; proxies to :9999)

So the service is UP. The fault is elsewhere.

## Reading the server log

```bash
tail -50 /mnt/z/pantheon/.hermes/logs/hindsight-server.log
```

Two tell-tale lines:

```
WARNING - hindsight_api.engine.providers.openai_compatible_llm - APIConnectionError (HTTP None), attempt 1: Request timed out.
WARNING - hindsight_api.worker.poller - [STUCK_STACK] op=... type=consolidation bank=hermes age=312s threshold=300s stage=llm.openai.consolidation+structured
```

Interpretation:
- `Request timed out` from the LLM provider = the model endpoint the API calls
  is slow/unreachable at that moment. This is transient provider noise unless
  it repeats.
- `[STUCK_STACK] ... type=consolidation ... age>threshold` = a consolidation job
  for a bank (`hermes`) is wedged waiting on that LLM call. The dashboard
  renders but any op behind consolidation stalls.

## Fix

Power-cycle the service to drop the in-flight wedged task (new PID = no stale
pending op loaded from memory):

```bash
systemctl --user restart pantheon-hindsight.service
sleep 10
systemctl --user status pantheon-hindsight.service   # active (running), new Main PID
curl -s http://127.0.0.1:8888/health                 # healthy + db connected
```

Startup banner confirms the provider/model actually in use (good place to spot
a wrong or slow model):

```
LLM: openai / accounts/fireworks/models/deepseek-v4-flash-0731
Embeddings: openai
Reranker: rrf
```

## Benign init noise after restart (do NOT chase)

- `metrics: MetricReader.__init__() got an unexpected keyword argument
  'otel_component_type'. Metrics will be disabled` — init-order warning only.
- `LLM trace write failed ... PostgreSQLBackend is not initialized. Call
  initialize() first` — startup ordering; self-resolves.

The one thing to keep an eye on after restart: do `Request timed out` lines stop?
If they recur, the provider endpoint itself is the problem (check reachability
from this box / whether the model ID is still valid), not the service.
