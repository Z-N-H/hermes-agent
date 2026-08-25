---
name: llm-observability
description: >-
  Instrument LLM applications with OpenTelemetry tracing, Arize Phoenix, and
  runtime observability. Covers span placement, graceful fallback, and common
  pitfalls when tracing agentic systems built on Pantheon + Hermes.
triggers:
  - Adding Arize Phoenix or OpenTelemetry tracing to a project
  - Instrumenting LLM calls for observability
  - Setting up distributed tracing for AI agents
  - Debugging missing spans, wrong span names, or disconnected traces
  - Reviewing tracing code in Pantheon or Hermes
---

# LLM Observability

## End-to-End Verification: Confirming Spans Land in Phoenix

After writing instrumentation, always verify data actually reaches the collector:

```python
from phoenix.client import Client

client = Client(base_url="http://127.0.0.1:6006")

# Query spans for a project
spans = client.spans.get_spans(project_identifier="default")
for span in spans:
    print(f"  - {span['name']} ({span['span_id']})")

# Query traces
traces = client.traces.get_traces(project_identifier="default")
for trace in traces:
    print(f"  - {trace['trace_id']}")
```

**Verify these specific attributes exist:**
- `gen_ai.request.model` — model name (e.g. `claude-sonnet-4`)
- `gen_ai.usage.input_tokens` / `output_tokens` — token counts
- `gen_ai.system` — provider name (`anthropic`, `openai`, `synthetic`)
- `tool.name` / `tool.status` / `tool.duration_ms` — tool call metadata
- `hermes.task_id` / `session_id` / `turn_id` — Hermes context

If a span is missing or attributes are wrong, check:
1. The exporter endpoint is correct (`PHOENIX_COLLECTOR_ENDPOINT`)
2. The project name matches (`PHOENIX_PROJECT_NAME`)
3. The span was actually ended (common bug: exception before `span.end()`)
4. Force-flush the provider: `provider.force_flush()`

## Architecture Rule: Trace the Inference Layer, Not the Orchestration Layer

In the Pantheon + Hermes stack:

- **Pantheon** orchestrates agents — it spawns Claude Code, OpenCode, etc. as sandboxed subprocesses via `worker_pool.py` / `sandbox_mgr.run_sandboxed()`.
- **Hermes** performs actual LLM inference — it calls `generate()` on model clients in `agent/chat_completion_helpers.py` and the provider adapter layer.

**Place `llm.invoke` spans at the Hermes inference layer**, where the actual HTTP/API call to the model provider happens. Do NOT wrap Pantheon's subprocess spawning or sandbox execution with `llm.invoke` — those trace agent process lifecycles, not LLM calls.

### Correct Span Placement

| What you're tracing       | Correct span name      | Correct location                              |
|---------------------------|------------------------|-----------------------------------------------|
| Actual LLM API call       | `llm.invoke`           | Hermes model client / completion helpers      |
| Agent subprocess spawn    | `worker.spawn`         | Pantheon `worker_pool.py`                     |
| Agent lifecycle/heartbeat | `agent.lifecycle`      | Pantheon `agent_tracker.py`                   |
| Tool execution            | `tool.invoke`          | Hermes tool execution layer                   |

## Graceful Fallback Pattern

Always provide a NoOp tracer so the application runs when Phoenix/OTel is unavailable:

```python
class NoOpSpan:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def set_attribute(self, k, v):
        pass

    def record_exception(self, e):
        pass


class NoOpTracer:
    def start_as_current_span(self, name, **kwargs):
        return NoOpSpan()
```

## Common Pitfalls

### P0 — Missing `input.value` / `output.value` (spans show `--` in Phoenix UI)
Phoenix's `input` and `output` columns are **not** auto-populated from `gen_ai.request.model` or `gen_ai.usage.*`. They specifically require `input.value` / `output.value` attributes on every span. Without them, the UI shows `--`.

**LLM spans:**
- `input.value` = formatted prompt (`[system] ...\n[user] ...`)
- `output.value` = assistant content

**Tool spans:**
- `input.value` = serialized args (JSON)
- `output.value` = result string

### P1 — Missing `session.id` / `openinference.span.kind` (no Sessions tab)
Phoenix groups spans into **Sessions** only when `session.id` is present on every span in the conversation. Also set `openinference.span.kind` (`"llm"` or `"tool"`) so Phoenix knows the span type.

Use `openinference.semconv.trace.SpanAttributes` for the standard keys, or fall back to raw `"session.id"` and `"openinference.span.kind"`.

### P2 — Importing non-existent functions
**Verify function names exist before committing imports.** In task 288, `pantheon_init.py` imported `get_tracer_provider()` from the tracing module, but the only function defined was `create_tracer_provider()`. This crashes the entire module on import — tests pass only because they never import `pantheon_init.py`.

**Fix:** Import the correct function, or better, avoid calling the init function at module level entirely.

### P3 — Tracing subprocesses as LLM calls
**Never wrap `sandbox_mgr.run_sandboxed(cmd, ...)` with an `llm.invoke` span.** That subprocess runs for minutes or hours and makes its own internal LLM calls. The span duration, semantics, and attributes are completely wrong.

**What happens:** The span covers the entire agent session (minutes) instead of a single LLM call (seconds). Phoenix shows one giant `llm.invoke` instead of the actual per-call traces.

**Fix:** Use `worker.spawn` or `agent.lifecycle` for subprocess-level tracing. Keep `llm.invoke` for the actual model API call.

### P4 — Span context loss across subprocess boundaries
Subprocesses break OTel span context automatically. Spans inside Claude Code (running in its own process) won't connect to Pantheon/Hermes spans without explicit context propagation (e.g., injecting `traceparent` via environment variables).

**Mitigation:** Either accept disconnected traces for agent subprocesses, or propagate the W3C trace context into the child process environment.

### P5 — Monkey-patching OpenAI clients in Hermes
**Do not monkey-patch `openai.resources.chat.completions.Completions.create` in Hermes.** Hermes already has a mature plugin hook system (`pre_api_request`, `post_api_request`, `pre_tool_call`, `post_tool_call`) that fires at exactly the right lifecycle points. The bundled `langfuse` plugin at `plugins/observability/langfuse/__init__.py` is the canonical reference implementation.

**What happens if you ignore this:** You fight Hermes's internal client lifecycle (clients are recreated per-request, custom timeout logic, retry wrappers, streaming adapters). The monkey-patch either misses calls or breaks during retries.

**Fix:** Write a plugin that registers `on_pre_api_request` / `on_post_api_request` via `ctx.register_hook()`. Hermes handles all the instrumentation plumbing.

### P6 — Installing OTel deps in Hermes venv
Hermes runs in a venv under `/mnt/z/pantheon/.hermes/hermes-agent/venv/`. Do NOT use plain `pip install` — PEP 668 blocks it as "externally managed". Use `uv` pointing at the venv's Python:

```bash
cd /mnt/z/pantheon/.hermes/hermes-agent
uv pip install --python venv/bin/python arize-phoenix-otel opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
```

### P7 — Phoenix startup timeout on WSL drvfs
Phoenix's `strawberry` + `pydantic` imports can take **60–90 seconds** on WSL's `/mnt/z` drvfs. A `Type=simple` systemd service exits immediately and may fail health checks. Use `Type=oneshot` with `TimeoutStartSec=180` and port-waiting logic in the startup script.

See `references/phoenix-systemd-wsl.md` for the complete systemd + Tailscale setup.

## Standard Setup Pattern

1. `uv add arize-phoenix-otel`
2. Create a central `tracing.py` module with `create_tracer_provider()` + `get_tracer()`
3. Initialize the tracer at application startup (not at module level in unrelated files)
4. Instrument at actual LLM call sites in Hermes
5. Add NoOp fallback for when the Phoenix backend is down
6. Write tests that actually import the startup module to catch import bugs

## References

- `references/phoenix-task-288.md` — Full session transcript: the wrong span placement, the critical import bug, OpenCode review findings, and the corrected architecture understanding.
- `references/hermes-phoenix-plugin.md` — Complete implementation guide for a Hermes Phoenix observability plugin using the native hook system, including lazy tracer init, NoOp fallback, in-memory span state, subprocess.Popen monkey-patch for TRACEPARENT propagation, safe attribute serialization, and Phoenix UI attributes (`input.value`, `output.value`, `session.id`, `openinference.span.kind`).
- `references/hermes-phoenix-verification.md` — Step-by-step verification that spans actually land in Phoenix, including the Python client API, force-flush patterns, and TRACEPARENT propagation confirmation.
- `references/hermes-plugin-binary-download.md` — Pattern for plugins that need external binaries (ShellCheck, vet, etc.): auto-download on first use instead of committing large binaries to git.
- `references/phoenix-systemd-wsl.md` — Running Phoenix + Hermes dashboard as a systemd user service on WSL2, with Tailscale path registration, PID-based lifecycle, and handling slow `strawberry`/`pydantic` imports on drvfs.
