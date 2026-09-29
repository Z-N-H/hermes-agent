# Phoenix Observability Integration for Hermes

Hermes plugin that traces every LLM call and tool execution to Arize Phoenix via OpenTelemetry, with automatic trace context propagation across subprocess boundaries.

## Plugin Location

```
plugins/observability/phoenix/
├── plugin.yaml      # Manifest (hooks: pre/post api_request, pre/post tool_call)
├── __init__.py      # Tracing logic, span creation, TRACEPARENT injection
├── README.md        # Usage docs
└── tests/           # pytest suite
```

## What It Traces

| Span name | Fired by | Attributes |
|-----------|----------|------------|
| `llm.invoke` | `pre_api_request` / `post_api_request` hooks | `gen_ai.request.model`, `gen_ai.system`, `gen_ai.usage.*`, `hermes.task_id`, `hermes.session_id` |
| `tool.invoke` | `pre_tool_call` / `post_tool_call` hooks | `tool.name`, `tool.status`, `tool.duration_ms`, `hermes.*` |

## Phoenix UI Column Attributes (`input.value` / `output.value`)

**Critical:** Phoenix's `input` and `output` columns in the span table **only** populate when spans carry `input.value` and `output.value` attributes. Without these, the UI shows `--`.

| Span type | `input.value` | `output.value` | `input.mime_type` | `output.mime_type` |
|-----------|---------------|----------------|-------------------|--------------------|
| `llm.invoke` | Formatted prompt: `[system] ...\n[user] ...` | Assistant response content | `text/plain` | `text/plain` |
| `tool.invoke` | Tool args (JSON serialized) | Tool result (string/dict/serialized) | `application/json` | `text/plain` or `application/json` |

Set these attributes **on the span** before ending it:

```python
# LLM span — in on_pre_api_request
span.set_attribute("input.value", "[system] You are a helper.\n[user] What is 2+2?")
span.set_attribute("input.mime_type", "text/plain")

# LLM span — in on_post_api_request
span.set_attribute("output.value", "2+2 equals 4.")
span.set_attribute("output.mime_type", "text/plain")

# Tool span — in on_pre_tool_call (set in start_span attributes)
tracer.start_span("tool.invoke", attributes={
    "input.value": json.dumps({"command": "echo hello"}),
    "input.mime_type": "application/json",
    ...
})

# Tool span — in on_post_tool_call
span.set_attribute("output.value", "hello\n")
span.set_attribute("output.mime_type", "text/plain")
```

**Pitfall:** Setting `tool.arg.command` or `gen_ai.request.model` is not enough — Phoenix ignores these for the `input`/`output` columns. Only `input.value` and `output.value` matter for the UI.

## Key Technique: TRACEPARENT Propagation via subprocess.Popen Monkey-Patch

The plugin wraps `subprocess.Popen` so every child process (terminal, delegate_task, opencode, Pantheon workers) automatically receives the active W3C trace context in its environment:

```python
import subprocess

_ORIGINAL_POPEN = subprocess.Popen

def _popen_with_traceparent(*args, **kwargs):
    env = kwargs.get("env")
    if env is not None:
        _inject_traceparent_into_env(env)
    else:
        kwargs["env"] = _inject_traceparent_into_env(dict(os.environ))
    return _ORIGINAL_POPEN(*args, **kwargs)

subprocess.Popen = _popen_with_traceparent
```

Child processes (like Pantheon workers) read `TRACEPARENT` from `os.environ` on startup and call `extract_trace_context()` to attach to the parent trace.

## W3C Trace Context Helpers

```python
def inject_trace_context(env: dict) -> dict:
    """Inject TRACEPARENT into env dict for subprocess spawning."""
    ...

def extract_trace_context(env: dict | None = None) -> Context | None:
    """Read TRACEPARENT from env and return an OTel Context."""
    ...

def get_current_traceparent() -> str | None:
    """Get the current span's W3C traceparent string."""
    ...
```

## Lazy OTel Loading

The plugin uses lazy imports so Hermes does not crash if dependencies are missing:

```python
_OTEL_AVAILABLE = False
try:
    from opentelemetry import trace as _otel_trace
    _OTEL_AVAILABLE = True
except ImportError:
    pass
```

When OTel is unavailable, a `_NoOpTracer` is used — spans are created but silently dropped.

## Dependencies

Install into Hermes venv:
```bash
uv pip install --python venv/bin/python arize-phoenix-otel opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
```

**Pitfall:** If Phoenix is installed in the Hermes venv alongside an older `anthropic` package, Phoenix may fail to start with:
```
ImportError: cannot import name 'AsyncAnthropicBedrockMantle' from 'anthropic'
```
Fix: upgrade `anthropic` in the venv:
```bash
uv pip install --python venv/bin/python 'anthropic>=0.40.0'
```
Phoenix's `pydantic-ai-slim` dependency requires a newer `anthropic` than Hermes may have installed.

**Pitfall (WSL drvfs):** Phoenix's first import of `strawberry` + `pydantic` can take **20–60 seconds** on WSL2 when the venv lives on `/mnt/z` (9P filesystem). The process appears hung or silent. It is not broken — just slow. Use a generous timeout when checking if Phoenix is ready:
```bash
timeout 120 bash -c 'until curl -s http://127.0.0.1:6006 > /dev/null; do sleep 2; done'
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://127.0.0.1:6006/v1/traces` | OTLP trace endpoint |
| `PHOENIX_PROJECT_NAME` | `hermes` | Project name in Phoenix |
| `PHOENIX_DEBUG` | unset | Enable debug logging |

## Enabling the Plugin

```bash
hermes plugins enable observability/phoenix
```

Verify:
```bash
hermes plugins list  # should show observability/phoenix
```

## Verification (End-to-End)

```python
from opentelemetry import trace
provider = trace.get_tracer_provider()
# Force flush after test spans
provider.force_flush()
```

Then query Phoenix:
```python
from phoenix.client import Client
client = Client(base_url='http://127.0.0.1:6006')
spans = client.spans.get_spans(project_identifier='hermes')
for span in spans:
    print(f"  - {span.get('name')} ({span.get('span_id')})")
```

## Pantheon Worker Integration

Pantheon workers also trace to Phoenix:
- `worker.py` span: `agent.subprocess` (wraps sandboxed subprocess execution)
- `worker_pool.py` injects `TRACEPARENT` into spawned worker env vars
- `tracing.py` provides `inject_trace_context()` / `extract_trace_context()` helpers

The Pantheon tracer is initialized on startup in `pantheon_init.py` with a `BatchSpanProcessor` exporting to the same Phoenix endpoint.

## Testing

```bash
cd /mnt/z/pantheon/.hermes/hermes-agent
source venv/bin/activate
python -m pytest plugins/observability/phoenix/tests/ -v
```

9 tests cover: module loading, no-op fallback, span creation, TRACEPARENT injection into subprocesses.
