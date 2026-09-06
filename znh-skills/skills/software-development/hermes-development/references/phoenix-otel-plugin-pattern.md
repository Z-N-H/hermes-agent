# Phoenix / Arize OTel Plugin Pattern for Hermes

Reference implementation pattern for adding Arize Phoenix OpenTelemetry tracing to Hermes, derived from the existing Langfuse observability plugin.

## Where to place instrumentation

**Wrong:** Wrapping `subprocess.Popen()` or `sandbox_mgr.run_sandboxed()` with a span named `llm.invoke`. That subprocess is an external agent (Claude Code, OpenCode, etc.) that runs for minutes and makes its own LLM calls. The span misrepresents what it traces.

**Right:** Use Hermes' existing `pre_api_request` / `post_api_request` hooks. These fire at the actual `chat.completions.create()` boundary — the real LLM inference call.

## Hook mapping

| What to trace | Hermes hook | Span name | Attributes to capture |
|---------------|-------------|-----------|----------------------|
| LLM API call | `pre_api_request` / `post_api_request` | `llm.invoke` | model, provider, stream, temperature, tokens.prompt, tokens.completion, tokens.total, finish_reason |
| Tool execution | `pre_tool_call` / `post_tool_call` | `tool.invoke` | tool_name, tool_args (redacted), status, error.type |
| Conversation turn | `pre_llm_call` / `post_llm_call` | `conversation.turn` | task_id, session_id, platform, turn_type |

## Reference: existing Langfuse plugin

The canonical implementation lives at:
```
plugins/observability/langfuse/__init__.py
plugins/observability/langfuse/plugin.yaml
```

Key functions to mirror:
- `on_pre_llm_request()` — starts a Langfuse generation observation from request metadata
- `on_post_llm_call()` — ends the observation with usage, cost, and output
- `on_pre_tool_call()` / `on_post_tool_call()` — starts/ends tool spans
- `register(ctx)` — maps hook names to the callbacks above

For Phoenix, replace Langfuse SDK calls with `opentelemetry.trace` calls:
```python
from opentelemetry import trace

tracer = trace.get_tracer("hermes", "0.16.0")

# In pre_api_request hook:
span = tracer.start_span("llm.invoke", attributes={"model": model, ...})

# In post_api_request hook:
span.set_attribute("tokens.total", usage.total_tokens)
span.end()
```

## Trace context propagation to Pantheon workers

When Hermes calls a Pantheon tool that spawns a worker process, the worker is a separate Python process. To keep the trace connected:

### 1. Hermes plugin injects TRACEPARENT into tool env

In the `pre_tool_call` hook (or before Pantheon dispatches a worker), serialize the current span context to W3C format:

```python
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

carrier = {}
TraceContextTextMapPropagator().inject(carrier)
traceparent = carrier.get(
    "traceparent"
)  # e.g. "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
# Pass traceparent into the tool's environment or args
```

### 2. Pantheon worker extracts TRACEPARENT on startup

In the Pantheon worker process, before creating any spans:

```python
import os
from opentelemetry.context import attach, detach
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

traceparent = os.environ.get("TRACEPARENT")
if traceparent:
    carrier = {"traceparent": traceparent}
    ctx = TraceContextTextMapPropagator().extract(carrier)
    token = attach(ctx)
    # ... create child spans here ...
    detach(token)
```

### 3. Pantheon `tracing.py` module

Pantheon should have a central `tracing.py` that:
- Initialises a tracer provider on module load (lazy, with graceful fallback)
- Exports `tracer` singleton
- Provides `inject_trace_context(env)` and `extract_trace_context(env)` helpers
- Uses `NoOpSpan` / `NoOpTracer` fallbacks when Phoenix/OTel is unavailable

```python
# agent_context/scripts/tracing.py
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class NoOpSpan:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def set_attribute(self, *a):
        pass

    def is_recording(self):
        return False

    def record_exception(self, *a):
        pass


class NoOpTracer:
    def start_as_current_span(self, *a, **k):
        return NoOpSpan()

    def start_span(self, *a, **k):
        return NoOpSpan()


def create_tracer_provider():
    try:
        from phoenix.otel import register

        port = os.getenv("PHOENIX_PORT", "6006")
        return register(endpoint=f"http://127.0.0.1:{port}/v1/traces")
    except Exception:
        return None


def get_tracer(provider=None):
    if provider is not None:
        try:
            return provider.get_tracer("pantheon", "0.2.0")
        except Exception:
            pass
    return NoOpTracer()


tracer = get_tracer(create_tracer_provider())


@contextmanager
def extract_trace_context(env: dict):
    traceparent = env.get("TRACEPARENT")
    if not traceparent:
        yield
        return
    token = None
    try:
        from opentelemetry.context import attach, detach
        from opentelemetry.trace.propagation.tracecontext import (
            TraceContextTextMapPropagator,
        )

        ctx = TraceContextTextMapPropagator().extract({"traceparent": traceparent})
        token = attach(ctx)
    except Exception:
        pass
    try:
        yield
    finally:
        if token is not None:
            try:
                detach(token)
            except Exception:
                pass


def inject_trace_context(env: dict) -> dict:
    try:
        from opentelemetry.trace.propagation.tracecontext import (
            TraceContextTextMapPropagator,
        )

        carrier = {}
        TraceContextTextMapPropagator().inject(carrier)
        tp = carrier.get("traceparent")
        if tp:
            env["TRACEPARENT"] = tp
    except Exception:
        pass
    return env
```

## Common mistakes

- **Importing a non-existent function.** `pantheon_init.py` once imported `get_tracer_provider` which didn't exist in `tracing.py`. The module-level initialisation (`tracer = get_tracer(create_tracer_provider())`) is sufficient — don't add redundant init calls in `pantheon_init.py`.
- **Missing trace context in subprocess env.** `subprocess.Popen()` without explicit `env=child_env` inherits `os.environ` but you must merge `TRACEPARENT` into it. The default `Popen` does not forward dynamically injected env vars.
- **Span naming confusion.** `llm.invoke` should mean "an LLM API call", not "an agent subprocess was launched". Be precise with span names.
