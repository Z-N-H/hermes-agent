# Hermes Phoenix Plugin — Session Verification Notes

Session: 2026-06-26 — Building and verifying the Hermes Phoenix observability plugin.

## What Was Built

### Hermes Plugin

```
plugins/observability/phoenix/
├── plugin.yaml          # manifest: hooks pre_api_request, post_api_request, pre_tool_call, post_tool_call
├── __init__.py          # 583-line plugin with lazy OTel init, NoOp fallback, TRACEPARENT propagation
├── README.md            # usage docs
└── tests/
    └── test_phoenix_plugin.py  # 9 tests, all passing
```

### Key features implemented

1. **LLM span tracing** — `llm.invoke` via `pre_api_request` / `post_api_request` hooks
   - Captures: model name, provider, token usage, finish reason, duration
   - Uses in-memory `_SPAN_STATE` dict keyed by `api_request_id` to pair pre/post

2. **Tool span tracing** — `tool.invoke` via `pre_tool_call` / `post_tool_call` hooks
   - Captures: tool name, args preview, status, duration, result preview
   - Uses in-memory `_SPAN_STATE` dict keyed by `tool_call_id`

3. **Subprocess TRACEPARENT propagation** — monkey-patches `subprocess.Popen`
   - Injects `TRACEPARENT` env var into every child process
   - Works for: terminal tool, delegate_task, opencode, any subprocess
   - Clean: copies `os.environ` when no env provided, injects into existing env when provided

4. **Lazy OTel init** — `_OTEL_AVAILABLE` flag, `_get_or_create_tracer()` caches tracer
   - No crash if dependencies missing
   - Uses `arize.phoenix.otel.register()` if available, falls back to basic OTLP

## Verification Steps Performed

### 1. Start Phoenix collector locally

```bash
cd /mnt/z/pantheon/.hermes/hermes-agent
source venv/bin/activate
phoenix serve --host 0.0.0.0 --port 6006
```

Health check: `curl -s http://127.0.0.1:6006/health` → returns 200 (HTML page)

### 2. Verify plugin loads correctly

```python
import sys

sys.path.insert(0, "/mnt/z/pantheon/.hermes/hermes-agent")
import plugins.observability.phoenix as phoenix

print(phoenix._OTEL_AVAILABLE)  # True
```

### 3. Run unit tests

```bash
python -m pytest plugins/observability/phoenix/tests/test_phoenix_plugin.py -v
# 9 passed in 2.16s
```

### 4. Verify spans land in Phoenix

```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

provider = TracerProvider()
provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="http://127.0.0.1:6006/v1/traces"))
)
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("test")
with tracer.start_as_current_span("test-span") as span:
    span.set_attribute("test.attr", "value")

provider.force_flush()
```

### 5. Query Phoenix for received spans

```python
from phoenix.client import Client

client = Client(base_url="http://127.0.0.1:6006")

spans = client.spans.get_spans(project_identifier="default")
for span in spans:
    print(f"  - {span['name']}")
```

**Result:** Spans found:
- `llm.invoke` — with `gen_ai.request.model`, `gen_ai.usage.input_tokens`, etc.
- `tool.invoke` — with `tool.name`, `tool.status`, `tool.duration_ms`, etc.
- `test-parent` — parent span from subprocess test
- `test_subprocess` — child span from subprocess that received TRACEPARENT

### 6. Verify TRACEPARENT propagation

```python
import subprocess
from plugins.observability.phoenix import (
    _get_or_create_tracer,
    _install_subprocess_patch,
)

_install_subprocess_patch()
tracer = _get_or_create_tracer()

with tracer.start_as_current_span("test"):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('TRACEPARENT', 'NOT_FOUND'))",
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout.strip())
    # Output: 00-dbb86e3e2907c0c38b89b5c3e899de0e-968b40d1498e33b5-03
```

**Result:** Subprocess correctly received W3C TRACEPARENT header.

## Dependencies Installed

```bash
uv pip install --python venv/bin/python \
  arize-phoenix-otel opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp pytest
```

Packages installed:
- `arize-phoenix-otel==0.16.1`
- `opentelemetry-api==1.43.0`
- `opentelemetry-sdk==1.43.0`
- `opentelemetry-exporter-otlp==1.43.0`
- `opentelemetry-proto==1.43.0`
- `opentelemetry-semantic-conventions==0.64b0`

## PR Created

Hermes PR: https://github.com/Z-N-H/hermes-agent/pull/1
- Branch: `znh/custom` pushed to fork `Z-N-H/hermes-agent`
- Contains: Phoenix observability plugin + ShellCheck security plugin

## Files

- `/mnt/z/pantheon/.hermes/hermes-agent/plugins/observability/phoenix/__init__.py` — complete implementation
- `/mnt/z/pantheon/.hermes/hermes-agent/plugins/observability/phoenix/plugin.yaml` — manifest
- `/mnt/z/pantheon/.hermes/hermes-agent/plugins/observability/phoenix/tests/test_phoenix_plugin.py` — 9 tests
