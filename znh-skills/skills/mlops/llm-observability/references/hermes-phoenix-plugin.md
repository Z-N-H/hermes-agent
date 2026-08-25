# Hermes Phoenix Plugin — Implementation Reference

Session: 2026-06-26 — Building a Phoenix OTel observability plugin for Hermes.

## The Right Integration Point

Hermes already has a plugin hook system. Do NOT monkey-patch OpenAI clients. The bundled `langfuse` plugin at `plugins/observability/langfuse/__init__.py` is the canonical reference.

### Hooks available for observability

| Hook name | When it fires | What to trace |
|-----------|--------------|---------------|
| `pre_api_request` | Before Hermes sends a message to the LLM API | Start `llm.invoke` span |
| `post_api_request` | After Hermes receives the LLM response | End `llm.invoke` span, record usage |
| `pre_tool_call` | Before a tool is executed | Start `tool.invoke` span |
| `post_tool_call` | After a tool finishes | End `tool.invoke` span, record result |

### How to register

```python
def register(ctx) -> None:
    ctx.register_hook("pre_api_request", on_pre_api_request)
    ctx.register_hook("post_api_request", on_post_api_request)
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    ctx.register_hook("post_tool_call", on_post_tool_call)
```

Hermes auto-discovers plugins from `plugins/<category>/<name>/` when `plugin.yaml` is present and the plugin is enabled via `hermes plugins enable <category>/<name>`.

## Plugin structure

```
plugins/observability/phoenix/
├── plugin.yaml          # manifest: name, version, hooks list
├── __init__.py          # main logic
├── README.md            # usage docs
└── tests/
    └── test_phoenix_plugin.py
```

### plugin.yaml

```yaml
name: phoenix
version: "1.0.0"
description: "Arize Phoenix OTel observability for Hermes"
author: NousResearch
requires_env:
  - PHOENIX_COLLECTOR_ENDPOINT
hooks:
  - pre_api_request
  - post_api_request
  - pre_tool_call
  - post_tool_call
```

## Key implementation patterns

### 1. Lazy tracer with graceful fallback

```python
try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.trace import SpanKind, Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import (
        TraceContextTextMapPropagator,
    )
    from opentelemetry.sdk.trace import TracerProvider as _SDKTracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    _OTEL_AVAILABLE = True
except Exception:
    _OTEL_AVAILABLE = False
    _otel_trace = None

try:
    from arize.phoenix.otel import register as _phoenix_register
except Exception:
    _phoenix_register = None


def _get_or_create_tracer():
    if not _OTEL_AVAILABLE:
        return _NoOpTracer()

    endpoint = os.environ.get(
        "PHOENIX_COLLECTOR_ENDPOINT", "http://127.0.0.1:6006/v1/traces"
    )
    project = os.environ.get("PHOENIX_PROJECT_NAME", "hermes")

    if _phoenix_register is not None:
        provider = _phoenix_register(endpoint=endpoint, project_name=project)
        return provider.get_tracer("hermes.phoenix")

    # Fallback: basic OTLP
    provider = _SDKTracerProvider()
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    _otel_trace.set_tracer_provider(provider)
    return provider.get_tracer("hermes.phoenix")
```

### 2. NoOpSpan / NoOpTracer for when OTel is absent

```python
class _NoOpSpan:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def set_attribute(self, k, v):
        pass

    def record_exception(self, e):
        pass

    def end(self):
        pass


class _NoOpTracer:
    def start_as_current_span(self, name, **kwargs):
        return _NoOpSpan()

    def start_span(self, name, **kwargs):
        return _NoOpSpan()
```

### 3. In-memory span state for async pre/post pairs

Hermes hooks fire at different times (pre before the call, post after). You need to store the span between them:

```python
import threading

_SPAN_STATE: Dict[str, Any] = {}
_STATE_LOCK = threading.Lock()

def on_pre_api_request(*, api_request_id: str = "", model: str = "", **kwargs):
    tracer = _get_or_create_tracer()
    key = api_request_id or f"req-{threading.get_ident()}"
    attrs = {"gen_ai.request.model": model, ...}
    span = tracer.start_span("llm.invoke", kind=SpanKind.CLIENT, attributes=attrs)
    with _STATE_LOCK:
        _SPAN_STATE[key] = {"span": span, "started_at": time.time()}

def on_post_api_request(*, api_request_id: str = "", usage: Any = None, **kwargs):
    key = api_request_id or f"req-{threading.get_ident()}"
    with _STATE_LOCK:
        state = _SPAN_STATE.pop(key, None)
    if not state:
        return
    span = state["span"]
    if isinstance(usage, dict):
        if usage.get("input_tokens"):
            span.set_attribute("gen_ai.usage.input_tokens", usage["input_tokens"])
    span.set_status(Status(StatusCode.OK))
    span.end()
```

### 4. TRACEPARENT propagation to subprocesses

The `pre_tool_call` hook can return a dict that gets merged into subprocess env. But the cleanest approach is to monkey-patch `subprocess.Popen` globally when the plugin loads:

```python
_SUBPROCESS_PATCHED = False
_ORIGINAL_POPEN = None


def _install_subprocess_patch():
    global _SUBPROCESS_PATCHED, _ORIGINAL_POPEN
    if _SUBPROCESS_PATCHED:
        return
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
    _SUBPROCESS_PATCHED = True
```

Register the patch in `register()`:

```python
def register(ctx) -> None:
    ctx.register_hook("pre_api_request", on_pre_api_request)
    ...
    _install_subprocess_patch()
```

### 5. Safe serialization for span attributes

Span attributes must be primitives (str, int, float, bool) or lists of primitives. Use a helper:

```python
def _safe_serialize(value: Any, max_len: int = 2000) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return (
            value
            if len(value) <= max_len
            else value[:max_len] + f"... [truncated {len(value) - max_len} chars]"
        )
    if isinstance(value, dict):
        return {
            str(k): _safe_serialize(v, max_len) for k, v in list(value.items())[:50]
        }
    if isinstance(value, (list, tuple)):
        return [_safe_serialize(v, max_len) for v in list(value)[:50]]
    return _safe_serialize(repr(value), max_len)
```

## Attribute naming conventions

Use OpenInference semantic conventions where available:

- `gen_ai.system` — provider name (`openai`, `anthropic`, `synthetic`)
- `gen_ai.request.model` — model name
- `gen_ai.request.max_tokens` / `temperature` / `top_p`
- `gen_ai.usage.input_tokens` / `output_tokens` / `cache_read_tokens` / `cache_write_tokens` / `reasoning_tokens`
- `gen_ai.response.finish_reason` / `model` / `tool_call_count`
- `tool.name` / `tool.status` / `tool.duration_ms`
- `hermes.task_id` / `session_id` / `turn_id` / `api_call_count`

## Phoenix UI attributes (required for full feature coverage)

Phoenix renders **input** / **output** columns and **Sessions** tab only when specific attributes are present. Without these, spans show `--` in the UI.

### Input / Output content (every span)

| Attribute | What to set | Example |
|-----------|-------------|---------|
| `input.value` | The actual prompt text or tool args | `[system] You are a helper.\n[user] What is 2+2?` |
| `input.mime_type` | Format hint | `text/plain` or `application/json` |
| `output.value` | The actual response text or tool result | `2+2 equals 4.` |
| `output.mime_type` | Format hint | `text/plain` or `application/json` |

**For LLM spans:**
- `input.value` = formatted prompt messages (concatenate `[role] content` lines)
- `output.value` = assistant message content

**For tool spans:**
- `input.value` = serialized tool arguments (JSON)
- `output.value` = tool result (string, dict, or repr)

### Session tracking (group spans into conversation threads)

Import OpenInference semantic conventions for the standard attribute keys:

```python
try:
    from openinference.semconv.trace import SpanAttributes

    _SpanAttributes = (
        SpanAttributes  # SESSION_ID, OPENINFERENCE_SPAN_KIND, INPUT_VALUE, OUTPUT_VALUE
    )
    _OI_AVAILABLE = True
except Exception:
    _OI_AVAILABLE = False
```

Set on **every** span (both LLM and tool):

| Attribute | Value for LLM | Value for tool |
|-----------|---------------|----------------|
| `session.id` | The Hermes `session_id` | Same `session_id` |
| `openinference.span.kind` | `"llm"` | `"tool"` |

Phoenix will then show a **Sessions** tab with a chatbot-like conversation history view, grouping all spans that share the same `session.id`.

Fallback if `openinference.semconv` is not installed — use raw string keys:
- `"session.id"` instead of `SpanAttributes.SESSION_ID`
- `"openinference.span.kind"` instead of `SpanAttributes.OPENINFERENCE_SPAN_KIND`

## Installing deps

Hermes venv is PEP 668 externally-managed. Use `uv`:

```bash
cd /mnt/z/pantheon/.hermes/hermes-agent
uv pip install --python venv/bin/python \
  arize-phoenix-otel opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp
```

## Enabling the plugin

```bash
hermes plugins enable observability/phoenix
```

Or via `hermes tools → Phoenix Observability`.

## Files from this session

- `/mnt/z/pantheon/.hermes/hermes-agent/plugins/observability/phoenix/__init__.py` — complete plugin implementation
- `/mnt/z/pantheon/.hermes/hermes-agent/plugins/observability/phoenix/plugin.yaml` — manifest
- `/mnt/z/pantheon/.hermes/hermes-agent/plugins/observability/phoenix/tests/test_phoenix_plugin.py` — 9 tests (all passing)
