# Phoenix Observability Plugin

Traces every LLM call and tool execution from Hermes to [Arize Phoenix](https://docs.arize.com/phoenix) via OpenTelemetry.

## What it traces

| Span name | Kind | Fired when |
|-----------|------|------------|
| `llm.invoke` | CLIENT | Hermes starts an API request to the LLM provider |
| `tool.invoke` | INTERNAL | Hermes starts executing a tool |

### LLM span attributes
- `gen_ai.system` — provider name (e.g. `openai`, `anthropic`, `synthetic`)
- `gen_ai.request.model` — model name (e.g. `claude-sonnet-4`, `MiniMax-M3`)
- `gen_ai.request.max_tokens` — max_tokens from the request
- `gen_ai.request.temperature` — temperature from the request
- `gen_ai.request.top_p` — top_p from the request
- `gen_ai.request.tool_count` — number of tools available
- `gen_ai.usage.input_tokens` — prompt tokens consumed
- `gen_ai.usage.output_tokens` — completion tokens consumed
- `gen_ai.usage.cache_read_tokens` — cache read tokens (if supported)
- `gen_ai.usage.cache_write_tokens` — cache write tokens (if supported)
- `gen_ai.usage.reasoning_tokens` — reasoning tokens (if supported)
- `gen_ai.response.finish_reason` — stop / length / tool_calls etc.
- `gen_ai.response.model` — actual model that served the response
- `gen_ai.response.tool_call_count` — number of tool calls in response
- `hermes.*` — Hermes-specific metadata (task_id, session_id, turn_id, platform, api_call_count, etc.)

### Tool span attributes
- `tool.name` — tool name (e.g. `terminal`, `web_search`, `delegate_task`)
- `tool.arg.*` — individual arguments (safe-serialised)
- `tool.status` — ok / error / blocked / cancelled
- `tool.duration_ms` — execution duration
- `tool.result.length` — result string length
- `tool.result.preview` — first 500 chars of result
- `error.type` / `error.message` — when status is error/blocked/cancelled
- `hermes.*` — task_id, session_id, turn_id, tool_call_id

## Activation

```bash
# 1. Install the SDK (if not already present)
pip install arize-phoenix-otel opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp

# 2. Enable the plugin
hermes plugins enable observability/phoenix

# 3. (Optional) Set the Phoenix endpoint
export PHOENIX_COLLECTOR_ENDPOINT=http://127.0.0.1:6006/v1/traces
export PHOENIX_PROJECT_NAME=hermes
```

Or via `hermes tools → Phoenix Observability`.

## Trace context propagation

When a tool spawns a subprocess (e.g. Pantheon worker, OpenCode, terminal),
the plugin injects a W3C `TRACEPARENT` header into the subprocess environment.
Child processes that support OTel (like Pantheon workers) extract this and
create spans as children of the parent trace — giving you a single end-to-end
trace in Phoenix.

## Debug mode

```bash
export PHOENIX_DEBUG=true
```

Logs every span start/end to the Hermes console at INFO level.

## Architecture

```
Hermes Agent
├─ pre_api_request → start "llm.invoke" span
├─ chat.completions.create()  ← actual LLM call
├─ post_api_request → end span with usage/response metadata
│
├─ pre_tool_call → start "tool.invoke" span + inject TRACEPARENT
├─ tool executes (possibly in subprocess with TRACEPARENT env)
├─ post_tool_call → end span with result/duration/status
│
└── Phoenix collector (http://127.0.0.1:6006/v1/traces)
    └── Visualised in Phoenix UI
```
