---
name: hindsight-operations
description: Use when Hindsight memory seems down, slow, or broken.
version: 1.0.0
platforms: [linux]
environments: [hermes]
metadata:
  hermes:
    tags: [hindsight, memory, service, operations, tailnet, consolidation, llm, devops]
---

# Hindsight Operations

Class-level umbrella for operating and troubleshooting the Hindsight memory
service on the bazzite host (the persistent memory bank Hermes' `hindsight_*`
tools talk to). NOT the same as authoring memories — this is about the service
that stores them.

## Topology (know this first)

- **API**: `hindsight-api` binds **127.0.0.1:8888 only** — localhost, NOT the
  tailnet IP. Any probe against `100.x.y.z:8888` will fail even when healthy.
- **Control-plane UI**: runs on **:9999** (bunx `hindsight-control-plane`,
  api-url `http://127.0.0.1:8888`). Served on the tailnet at the **root** of
  `https://bazzite.centaur-perch.ts.net/` (Next.js; root path → :9999).
- **systemd unit**: `pantheon-hindsight.service` (user session
  `systemctl --user`); single-instance (a prior bug was dual-spawner split).
  **It owns ONLY the API (:8888).** The separate `pantheon-stack.sh` script
  launches the UI + phoenix + hermes-dashboard as background bunx/node
  processes, NOT under this unit. Restarting the systemd unit does NOT touch
  the UI.
- **DB**: embedded Postgres (pg0) at `/home/znh/.pg0/instances/hindsight`,
  bank name `hermes`.
- **Health check**: `curl -s http://127.0.0.1:8888/health` →
  `{"status":"healthy","database":"connected"}`.

## Health Check

```bash
systemctl --user status pantheon-hindsight.service   # active (running)
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8888/health  # 200
curl -s -o /dev/null -w "%{http_code}\n" https://bazzite.centaur-perch.ts.net/  # 3xx = UI up
```

## The key trap: healthy service, operations still hang

`active (running)` + `health: healthy` + UI loads ≠ everything works.
LLM-backed ops (consolidation, extraction, summarization) can stall while the
service itself is fine. Symptom the user reports: "I can't access it properly
on the tailnet" / dashboard loads but memory ops never complete.

Diagnose with the server log:

```bash
tail -50 /mnt/z/pantheon/.hermes/logs/hindsight-server.log
```

Two tell-tale pairs:
- `WARNING - ...openai_compatible_llm - APIConnectionError (HTTP None), attempt 1: Request timed out.` — provider/model endpoint slow or unreachable at that moment.
- `WARNING - ...worker.poller - [STUCK_STACK] ... type=consolidation bank=hermes ... age>threshold stage=llm.openai.consolidation+structured` — a consolidation job wedged on that LLM call.

## Fix: restart clears the wedged task

```bash
systemctl --user restart pantheon-hindsight.service
sleep 10
systemctl --user status pantheon-hindsight.service   # active, NEW Main PID
curl -s http://127.0.0.1:8888/health                 # healthy + db connected
```

New PID = stale in-flight pending op is dropped, not reloaded. Then check
whether `Request timed out` lines recur — if they do, the provider endpoint /
model ID is the root cause (verify reachability + model validity), not the
service.

Startup banner is the best place to confirm provider/model actually in use:
```
LLM: openai / accounts/fireworks/models/deepseek-v4-flash-0731
Embeddings: openai
Reranker: rrf
MCP: enabled at /mcp
```

## Separate-dependent-component trap: restart the API, not the UI

`systemctl --user restart pantheon-hindsight.service` restarts ONLY the API.
If the symptom is "dashboard loads but shows no banks" or the bank dropdown is
stuck on a disabled **"Loading..."** button, that is a STALE UI problem, not an
API one — and an API restart will NOT fix it.

The dashboard UI (`:9999`) can run for days as a detached `bunx
hindsight-control-plane` process. When the API underneath is restarted, the
long-lived UI keeps serving an old client state and its bank-loading hook
silently never fires; the backend is fine the whole time.

Confirm the split in one shot (all from the same box):
- API is healthy but empty-bank symptom: `curl -s http://127.0.0.1:8888/v1/default/banks`
  → if it returns both banks (`hermes`, `claude_code`) with fact counts, the
  DATA is fine and the defect is UI-side.
- UI process age → stale: `ps -eo pid,etime,cmd | grep hindsight-control-plane`
  — `etime` of `N-days` means it predates the API restart.
- The actual APIS routes live under the `default` tenant:
  `curl .../v1/default/banks`, `/v1/default/banks/{bank_id}/health/llm`,
  `/v1/default/banks/{bank_id}/memories`, etc. (see `/openapi.json` for the
  full list).

Fix: kill the stale control-plane tree, then relaunch via the idempotent
stack wrapper (it port-guards every component, so with the API/phoenix/
dashboard up it ONLY restarts the freed :9999 UI and re-applies the proxy
patches):

```bash
# kill the stale UI tree (bun + its node children)
pkill -f "hindsight-control-plane"          # or exact PIDs: kill <node-server> <node-bin> <bun>
sleep 4
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9999/   # good: HTTP 000 / connection refused

# relaunch UI (idempotent; also re-registers tailscale paths — now a one-shot restart can't be skipped)
HOME=/home/znh /mnt/z/pantheon/vault/ZNH/scripts/pantheon-stack.sh start
```

Then the dashboard dropdown should list both banks. This pitfall was hit
2026-08-16: an API-only restart left a 12-day-old UI stuck on "Loading..." until
the UI process was replaced.

## Benign init noise after restart — do NOT chase

- `Failed to initialize metrics: ... 'otel_component_type'. Metrics will be disabled (using no-op collector).` — init-order warning, harmless.
- `LLM trace write failed ... PostgreSQLBackend is not initialized. Call initialize() first.` — startup ordering, self-resolves.

## Verify end-to-end after recovery

Hit the recall path to prove the backend LLM/DB round-trip works, not just the
health endpoint: `hindsight_recall` (or an equivalent) for a known fact.

## References

- `references/hindsight-stuck-consolidation-llm-timeout.md` — full 2026-08-16
  diagnosis transcript, symptom→log→fix walkthrough.
- `references/stale-ui-empty-bank-2026-08-16.md` — "dashboard shows no banks /
  stuck Loading" when the API is fine: stale long-lived UI control plane, and
  the API-vs-UI restart split.

## Related / overlap

- `pantheon-operations` (USER-OWNED) §2 "Hindsight Memory Service" carries
  health check + fact-extraction-model-deprecation and recall-failure subsections,
  plus the broader stack (cron, dashboard/tailscale exposure, projects). If
  adopted (`hermes curator adopt pantheon-operations`), fold this umbrella's
  stuck-consolidation/recovery content in there and retire this skill.
