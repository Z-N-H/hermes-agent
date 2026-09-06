# Phoenix Task 288 Session Notes

## Context
Task 288: `feat/288-add-arize-phoenix-otel-tracing-to-pantheon-llm-ops`
Purple Phoenix worktree: `/mnt/z/pantheon/projects/purple-phoenix/tasks/288-add-arize-phoenix-otel-tracing-to-pantheon-llm-ops/`

## What Was Built

### Commit chain (newest → oldest)
1. `9bce51d` — test: 21 tests for Phoenix OTEL tracing integration (`tests/test_tracing.py`)
2. `fce9e29` — feat: initialize Phoenix tracer on Pantheon startup (`pantheon_init.py`)
3. `e5364bf` — feat: instrument agent launches, LLM calls, worker spawns (`worker.py`, `worker_pool.py`, `agent_tracker.py`)
4. `7ac63e4` — feat: add Phoenix OTEL tracing module with graceful fallback (`tracing.py`)
5. `9ff4cbb` — deps: add `arize-phoenix-otel`

### Files touched
- `agent_context/scripts/tracing.py` — new module with `NoOpSpan`, `NoOpTracer`, `create_tracer_provider()`, `get_tracer()`
- `agent_context/scripts/pantheon_init.py` — tracer init + import of `get_tracer_provider()`
- `agent_context/scripts/worker.py` — `llm.invoke` span wrapping `sandbox_mgr.run_sandboxed()`
- `agent_context/scripts/worker_pool.py` — `worker.spawn` span wrapping `subprocess.Popen()`
- `agent_context/scripts/agent_tracker.py` — `agent.lifecycle` span in context manager
- `tests/test_tracing.py` — 21 tests

## The Critical Bug (P0)

```python
# agent_context/scripts/pantheon_init.py
from agent_context.scripts.tracing import get_tracer_provider  # ❌ DOES NOT EXIST

get_tracer_provider()  # ❌ ImportError on startup
```

The actual function in `tracing.py` is `create_tracer_provider()`. OpenCode caught this during review. The 21 tests pass only because they import `tracing.py` directly — they never import `pantheon_init.py`.

**Root cause:** Agent (Kimi K2.6) wrote the import without verifying the function name. This is a general pitfall when splitting code across modules.

## The Architecture Misunderstanding

### What was done wrong
`worker.py` wrapped the agent subprocess spawn with `llm.invoke`:

```python
with tracer.start_as_current_span("llm.invoke", attributes=span_attrs) as span:
    result = sandbox_mgr.run_sandboxed(cmd, sandbox_config, ...)
```

This is wrong because:
- `sandbox_mgr.run_sandboxed()` spawns Claude Code / OpenCode as a subprocess
- That subprocess runs for **minutes to hours**
- Inside that subprocess, Claude Code makes its **own** LLM calls via the Anthropic API
- The Pantheon/Hermes process has no visibility into those internal calls
- So `llm.invoke` here traces **agent execution time**, not **LLM inference time**

### User correction
> "I'm not sure this is right? It shouldn't be wrapping Claude processes. It should be wrapping Hermes"

### Correct understanding
- **Pantheon** = orchestration layer (spawns agents, manages worktrees, tracks heartbeats)
- **Hermes** = inference layer (calls `generate()` on model clients, handles tool loops, streams tokens)
- Actual LLM calls happen in Hermes files like `agent/chat_completion_helpers.py`, `agent/anthropic_adapter.py`, `agent/openai_adapter.py`, etc.
- `llm.invoke` spans belong at the **model client call site** in Hermes
- Pantheon should trace **process lifecycle** (`worker.spawn`, `agent.lifecycle`) not **inference**

### What the spans actually trace now
| Span name | What it actually traces | What it should be named |
|-----------|------------------------|-------------------------|
| `llm.invoke` | Claude Code subprocess execution | `worker.spawn` or `agent.execution` |
| `worker.spawn` | `subprocess.Popen()` call | Correct — keep as-is |
| `agent.lifecycle` | AgentTracker heartbeat loop | Correct — keep as-is |

## Span Context Propagation Gap

No trace context is propagated into the spawned subprocess. Claude Code runs in its own process with its own OTel tracer (if any). The Pantheon and Claude Code traces will be completely disconnected in Phoenix.

**Mitigation options:**
1. Accept disconnected traces (simplest)
2. Inject `TRACEPARENT` env var into subprocess and configure Claude Code to use it
3. Move all LLM calls out of subprocesses (architectural change)

## OpenCode Review Findings

Run: `opencode run --dangerously-skip-permissions` with review prompt.

### P0 — Critical
- `pantheon_init.py` imports non-existent `get_tracer_provider()` → `create_tracer_provider()`

### P2 — Should Fix
1. Unused import: `from contextlib import contextmanager` in `tracing.py`
2. Duplicated logic: Permission-blocked detection computed twice in `worker.py`
3. Missing test coverage: `worker.py` spans (`llm.invoke`) and `worker_pool.py` spans have zero tests

### P3 — Design Observations
- No OTel span context propagation across subprocess boundaries
- `arize-phoenix-otel` is a hard dependency rather than optional
- `worker.spawn` span only covers `Popen()`, not actual worker execution

## Next Steps (from session)

User needs to decide:
1. Fix this Pantheon task — rename/remove misleading spans, fix import bug
2. Add Hermes-side tracing — instrument actual LLM calls in Hermes agent code
3. Both

## Related Files in Hermes (for future Hermes-side tracing)

Where actual LLM calls happen (not currently instrumented):
- `/mnt/z/pantheon/.hermes/hermes-agent/agent/chat_completion_helpers.py` — main completion logic
- `/mnt/z/pantheon/.hermes/hermes-agent/agent/anthropic_adapter.py` — Anthropic API calls
- `/mnt/z/pantheon/.hermes/hermes-agent/agent/openai_adapter.py` — OpenAI-compatible API calls
- `/mnt/z/pantheon/.hermes/hermes-agent/agent/auxiliary_client.py` — auxiliary/vision model calls

These are the correct locations for `llm.invoke` spans.
