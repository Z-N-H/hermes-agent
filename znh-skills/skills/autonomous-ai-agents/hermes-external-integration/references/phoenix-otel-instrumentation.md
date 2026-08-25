# Phoenix / Arize OTEL Safe Instrumentation Patterns

Condensed reference for instrumenting Python applications with [Arize Phoenix](https://github.com/Arize-ai/phoenix) OpenTelemetry tracing. Derived from the `feat/274-replace-agno-with-arize-phoenix-observability` branch work in Pantheon.

## Core Pattern: `tracing.py` — Lazy, Failsafe Tracer Module

Create a single `tracing.py` utility module that lazily initializes Phoenix and falls back to no-op when unavailable. All instrumentation code imports from this module, never from `phoenix.otel` or `opentelemetry` directly.

```python
"""Lazy OpenTelemetry tracing utilities for Phoenix observability."""

from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Optional

_tracer_provider = None
_tracer_cache: dict[str, Any] = {}
_initialized = False


def _init_phoenix() -> bool:
    """Initialize Phoenix tracer provider. Returns True if successful."""
    global _tracer_provider, _initialized

    if _initialized:
        return _tracer_provider is not None

    _initialized = True
    try:
        from phoenix.otel import register

        _tracer_provider = register(
            endpoint="http://127.0.0.1:6006/v1/traces",
            project_name="pantheon",
        )
        return True
    except Exception:
        _tracer_provider = None
        return False


def get_tracer(name: str) -> Any:
    """Get a tracer by name, with fallback to no-op tracer."""
    if name in _tracer_cache:
        return _tracer_cache[name]

    if _init_phoenix():
        try:
            from opentelemetry import trace

            tracer = trace.get_tracer(name)
            _tracer_cache[name] = tracer
            return tracer
        except Exception:
            pass

    _tracer_cache[name] = _NoOpTracer()
    return _tracer_cache[name]


class _NoOpSpan:
    """No-op span that absorbs all operations."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def add_event(self, name: str, attributes: Optional[dict] = None) -> None:
        pass

    def record_exception(self, exception: Exception) -> None:
        pass

    def end(self) -> None:
        pass

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _NoOpTracer:
    """No-op tracer that returns no-op spans."""

    def start_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()


def span(name: Optional[str] = None) -> Callable:
    """Decorator to wrap a function as an OTel span."""

    def decorator(func: Callable) -> Callable:
        span_name = name or f"pantheon.{func.__name__}"

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            module = getattr(func, "__module__", None) or "pantheon"
            tracer = get_tracer(module)
            with tracer.start_span(span_name) as s:
                return func(*args, **kwargs)

        return wrapper

    return decorator


@contextmanager
def SpanContext(tracer_name: str, span_name: str, attributes: Optional[dict] = None):
    """Context manager for manual span creation."""
    tracer = get_tracer(tracer_name)
    with tracer.start_span(span_name) as s:
        if attributes:
            for key, value in attributes.items():
                s.set_attribute(key, value)
        yield s
```

## API Traps (Learned the Hard Way)

1. **`span.end()` NOT `span.__exit__()`**: OpenTelemetry `tracer.start_span()` returns a `Span` object, not a context manager. `span.end()` is the correct termination method. `span.__exit__()` will throw `AttributeError` on real spans.

2. **`span.set_attribute(key, value)` NOT `span.set_attributes({...})`**: The standard OpenTelemetry Python API uses the singular `set_attribute`. The plural `set_attributes` exists on some implementations but is not part of the base API. Use a loop:
   ```python
   for key, value in attributes.items():
       span.set_attribute(key, value)
   ```

3. **NEVER call `register()` in hot paths**: `phoenix.otel.register()` initializes a full OTLP exporter batch processor. Calling it per-tool-call (e.g., inside a `post_tool_use` hook that runs dozens of times per session) kills performance and creates duplicate trace IDs. Initialize once at module level (lazy, cached) and reuse.

4. **Graceful fallback is mandatory**: The tracing layer must be completely optional. If `arize-phoenix-otel` is not installed, Phoenix is not running, or the endpoint is unreachable, the application must work identically. Every tracing call is wrapped in `try/except`.

## Instrumentation Patterns by Layer

### Worker spawn (`worker_pool.py`)
```python
from .tracing import get_tracer

tracer = get_tracer(__name__)
span = tracer.start_span("pantheon.agent.spawn")
try:
    span.set_attribute("worker_id", worker_id)
    span.set_attribute("task_id", task.task_id)
    span.set_attribute("project", task.project)
except Exception:
    pass
# ... spawn logic ...
try:
    span.end()
except Exception:
    pass
```

### Agent session (`worker.py`)
```python
tracer = get_tracer(__name__)
span = tracer.start_span("pantheon.agent.session")
try:
    span.set_attribute("task_id", self.task_id)
    span.set_attribute("project", self.project)
    span.set_attribute("worker_id", self.worker_id)
except Exception:
    pass
try:
    return self._run_impl()
finally:
    try:
        span.end()
    except Exception:
        pass
```

### Scheduler loop (`daemon.py`)
```python
tracer = get_tracer(__name__)
span = tracer.start_span("pantheon.scheduler.process_queue")
try:
    self._process_queue_impl()
finally:
    try:
        span.end()
    except Exception:
        pass
```

### Agent tracker context manager (`agent_tracker.py`)
```python
# In __enter__:
try:
    tracer = get_tracer(__name__)
    self._span = tracer.start_span("pantheon.agent.tracker")
    self._span.set_attribute("model", self.model)
    self._span.set_attribute("agent_type", self.agent_type)
except Exception:
    self._span = None

# In __exit__:
if self._span is not None:
    try:
        self._span.set_attribute("tokens_used", self._tokens)
        self._span.end()
    except Exception:
        pass
    self._span = None
```

## What NOT to Instrument

- **Subprocess hooks (`post_tool_use.py`)**: Hooks that run inside Claude Code or opencode subprocesses should NOT emit Phoenix spans directly. The subprocess may not have network access to `127.0.0.1:6006`, and calling `register()` per-tool-call is pathological. Instead, aggregate tool call counts in `.task.json` and emit them as attributes on the parent session span in `agent_tracker.py`.
- **Per-token spans**: Token counting is high-frequency. Record it as a span attribute on the session span, not as individual spans.

## Testing

```bash
# Verify no-op fallback works when Phoenix is down
python -c "from agent_context.scripts.tracing import get_tracer; print(get_tracer('test'))"
# Expected: <agent_context.scripts.tracing._NoOpTracer object at 0x...>
```

## Related

- `hermes-external-integration` SKILL.md — Decision guide for observability integration patterns
- `docs/PHOENIX_OBSERVABILITY.md` (in Pantheon) — Server setup and configuration
