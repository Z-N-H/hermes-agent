"""phoenix — Hermes plugin for Arize Phoenix observability.

Traces Hermes LLM calls and tool executions to Arize Phoenix via
OpenTelemetry.  Every ``pre_api_request`` / ``post_api_request`` pair
creates an ``llm.invoke`` span; every ``pre_tool_call`` / ``post_tool_call``
pair creates a ``tool.invoke`` span.  Trace context is propagated to
subprocess tools (Pantheon workers, OpenCode, terminal, etc.) via the
W3C ``TRACEPARENT`` environment variable so child spans link correctly.

Activation is handled by the Hermes plugin system — the plugin only loads
when listed in ``plugins.enabled`` (via ``hermes plugins enable
observability/phoenix`` or ``hermes tools → Phoenix Observability``).
At runtime it also requires the ``arize-phoenix-otel`` SDK; if missing
the hooks are inert.

Required env vars (set via ``hermes tools`` or ~/.hermes/.env):
  PHOENIX_COLLECTOR_ENDPOINT  - Phoenix OTLP endpoint (default: http://127.0.0.1:6006/v1/traces)

Optional env vars:
  PHOENIX_PROJECT_NAME          - Phoenix project name (default: "hermes")
  PHOENIX_DEBUG                 - set to "true" for verbose plugin logging
"""
from __future__ import annotations

import logging
import os
import threading
import time
import traceback
from contextlib import contextmanager
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────
# Lazy OTel imports — fail-open when optional deps are missing
# ──────────────────────────────────────────────────────────────────────────

_TRACER_PROVIDER: Any = None
_TRACER: Any = None
_OTEL_AVAILABLE = False
_SpanKind: Any = None
_Status: Any = None
_StatusCode: Any = None

try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.trace import SpanKind, Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    from opentelemetry.sdk.trace import TracerProvider as _SDKTracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    _OTEL_AVAILABLE = True
    _SpanKind = SpanKind
    _Status = Status
    _StatusCode = StatusCode
except Exception as _exc:
    logger.debug("phoenix plugin: opentelemetry SDK not available (%s)", _exc)
    _otel_trace = None  # type: ignore[assignment]
    TraceContextTextMapPropagator = None  # type: ignore[assignment,misc]


# OpenInference semantic conventions — lightweight, no heavy transitive imports
_SpanAttributes: Any = None
_OI_AVAILABLE = False
try:
    from openinference.semconv.trace import SpanAttributes
    _SpanAttributes = SpanAttributes
    _OI_AVAILABLE = True
except Exception as _exc:
    logger.debug("phoenix plugin: openinference.semconv not available (%s)", _exc)


try:
    from arize.phoenix.otel import register as _phoenix_register
except Exception as _exc:
    logger.debug("phoenix plugin: arize-phoenix-otel not available (%s)", _exc)
    _phoenix_register = None  # type: ignore[assignment]


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str) -> bool:
    value = _env(name).lower()
    return value in {"1", "true", "yes", "on"}


def _debug(msg: str) -> None:
    if _env_bool("PHOENIX_DEBUG"):
        logger.info("Phoenix tracing: %s", msg)


def _safe_serialize(value: Any, max_len: int = 2000) -> Any:
    """Best-effort serialisation for span attributes."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= max_len:
            return value
        return value[:max_len] + f"... [truncated {len(value) - max_len} chars]"
    if isinstance(value, dict):
        return {str(k): _safe_serialize(v, max_len) for k, v in list(value.items())[:50]}
    if isinstance(value, (list, tuple)):
        return [_safe_serialize(v, max_len) for v in list(value)[:50]]
    return _safe_serialize(repr(value), max_len)


def _set_session_and_kind(span: Any, session_id: str, kind: str) -> None:
    """Attach Phoenix session.id and openinference.span.kind to a span."""
    if span is None:
        return
    try:
        if session_id:
            if _OI_AVAILABLE and _SpanAttributes is not None:
                span.set_attribute(_SpanAttributes.SESSION_ID, session_id)
            else:
                span.set_attribute("session.id", session_id)
        if kind:
            if _OI_AVAILABLE and _SpanAttributes is not None:
                span.set_attribute(_SpanAttributes.OPENINFERENCE_SPAN_KIND, kind)
            else:
                span.set_attribute("openinference.span.kind", kind)
    except Exception:
        pass


def _get_or_create_tracer() -> Any:
    """Return a cached OTel tracer, or a no-op fallback."""
    global _TRACER_PROVIDER, _TRACER

    if _TRACER is not None:
        return _TRACER

    if not _OTEL_AVAILABLE:
        _TRACER = _NoOpTracer()
        return _TRACER

    endpoint = _env("PHOENIX_COLLECTOR_ENDPOINT", "http://127.0.0.1:6006/v1/traces")
    project_name = _env("PHOENIX_PROJECT_NAME", "hermes")

    # Try the Phoenix helper first (sets up BatchSpanProcessor, protobuf, etc.)
    if _phoenix_register is not None:
        try:
            _TRACER_PROVIDER = _phoenix_register(
                endpoint=endpoint,
                project_name=project_name,
            )
            _TRACER = _TRACER_PROVIDER.get_tracer("hermes.phoenix")
            _debug(f"registered via arize-phoenix-otel: endpoint={endpoint} project={project_name}")
            return _TRACER
        except Exception as exc:
            logger.warning("phoenix plugin: arize-phoenix-otel register failed (%s), falling back to basic OTLP", exc)

    # Fallback: manual SDK setup
    try:
        _TRACER_PROVIDER = _SDKTracerProvider()
        exporter = OTLPSpanExporter(endpoint=endpoint)
        _TRACER_PROVIDER.add_span_processor(BatchSpanProcessor(exporter))
        _otel_trace.set_tracer_provider(_TRACER_PROVIDER)
        _TRACER = _TRACER_PROVIDER.get_tracer("hermes.phoenix")
        _debug(f"registered via basic OTLP: endpoint={endpoint}")
        return _TRACER
    except Exception as exc:
        logger.warning("phoenix plugin: could not initialise tracer (%s)", exc)
        _TRACER = _NoOpTracer()
        return _TRACER


# ──────────────────────────────────────────────────────────────────────────
# In-memory span state
# ──────────────────────────────────────────────────────────────────────────

_SPAN_STATE: Dict[str, Any] = {}
_STATE_LOCK = threading.Lock()


def _req_key(api_request_id: str) -> str:
    return api_request_id or f"req-{threading.get_ident()}-{time.time():.6f}"


def _tool_key(tool_call_id: str, tool_name: str) -> str:
    return tool_call_id or f"tool-{tool_name}-{threading.get_ident()}-{time.time():.6f}"


# ──────────────────────────────────────────────────────────────────────────
# TRACEPARENT propagation for subprocess tools
# ──────────────────────────────────────────────────────────────────────────

def _inject_traceparent_into_env(env: Dict[str, str]) -> Dict[str, str]:
    """Inject the current W3C traceparent into *env* for child processes.

    Returns *env* (mutated in place) so callers can pass it straight to
    ``subprocess.Popen(..., env=env)``.
    """
    if not _OTEL_AVAILABLE or TraceContextTextMapPropagator is None:
        return env
    try:
        carrier: Dict[str, str] = {}
        TraceContextTextMapPropagator().inject(carrier)
        traceparent = carrier.get("traceparent")
        if traceparent:
            env["TRACEPARENT"] = traceparent
            _debug(f"injected TRACEPARENT={traceparent[:50]}...")
    except Exception as exc:
        logger.debug("phoenix plugin: failed to inject traceparent: %s", exc)
    return env


def get_current_traceparent() -> Optional[str]:
    """Return the current W3C traceparent string, or None if no span is active."""
    if not _OTEL_AVAILABLE or TraceContextTextMapPropagator is None:
        return None
    try:
        carrier: Dict[str, str] = {}
        TraceContextTextMapPropagator().inject(carrier)
        return carrier.get("traceparent")
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────
# No-op tracer (used when OTel is unavailable)
# ──────────────────────────────────────────────────────────────────────────

class _NoOpSpan:
    """Drop-in replacement for OTel Span when the SDK is absent."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def record_exception(self, exception: Any) -> None:
        pass

    def end(self, end_time: Optional[Any] = None) -> None:
        pass

    def update_name(self, name: str) -> None:
        pass

    def get_span_context(self):
        if _OTEL_AVAILABLE and _otel_trace is not None:
            from opentelemetry.trace import INVALID_SPAN_CONTEXT
            return INVALID_SPAN_CONTEXT
        return None


class _NoOpTracer:
    """Drop-in replacement for OTel Tracer when the SDK is absent."""

    def start_as_current_span(
        self,
        name: str,
        context: Optional[Any] = None,
        kind: Optional[Any] = None,
        attributes: Optional[Dict[str, Any]] = None,
        links: Optional[Any] = None,
        start_time: Optional[Any] = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
    ):
        return _NoOpSpan()

    def start_span(
        self,
        name: str,
        context: Optional[Any] = None,
        kind: Optional[Any] = None,
        attributes: Optional[Dict[str, Any]] = None,
        links: Optional[Any] = None,
        start_time: Optional[Any] = None,
    ):
        return _NoOpSpan()


# ──────────────────────────────────────────────────────────────────────────
# Hook handlers
# ──────────────────────────────────────────────────────────────────────────

def on_pre_api_request(
    *,
    task_id: str = "",
    turn_id: str = "",
    api_request_id: str = "",
    session_id: str = "",
    user_message: Any = None,
    conversation_history: Any = None,
    platform: str = "",
    model: str = "",
    provider: str = "",
    base_url: str = "",
    api_mode: str = "",
    api_call_count: int = 0,
    request_messages: Any = None,
    message_count: int = 0,
    tool_count: int = 0,
    approx_input_tokens: int = 0,
    request_char_count: int = 0,
    max_tokens: Any = None,
    started_at: float = 0.0,
    middleware_trace: Any = None,
    request: Any = None,
    **_: Any,
) -> None:
    """Start an ``llm.invoke`` span when Hermes begins an API request."""
    tracer = _get_or_create_tracer()
    key = _req_key(api_request_id)

    attrs: Dict[str, Any] = {
        "gen_ai.system": provider or "unknown",
        "gen_ai.request.model": model or "unknown",
        "gen_ai.request.max_tokens": max_tokens if max_tokens is not None else 0,
        "gen_ai.request.tool_count": tool_count,
        "hermes.api_call_count": api_call_count,
        "hermes.task_id": task_id or "",
        "hermes.session_id": session_id or "",
        "hermes.turn_id": turn_id or "",
        "hermes.platform": platform or "",
        "hermes.api_mode": api_mode or "",
        "hermes.base_url": (base_url or "")[:200],
        "hermes.message_count": message_count,
        "hermes.approx_input_tokens": approx_input_tokens,
    }

    # Include temperature / top_p if present in the request payload
    try:
        if isinstance(request, dict):
            body = request.get("body", {})
            if isinstance(body, dict):
                if "temperature" in body:
                    attrs["gen_ai.request.temperature"] = body["temperature"]
                if "top_p" in body:
                    attrs["gen_ai.request.top_p"] = body["top_p"]
    except Exception:
        pass

    try:
        span = tracer.start_span("llm.invoke", kind=_SpanKind.CLIENT, attributes=attrs)
    except Exception as exc:
        logger.debug("phoenix plugin: failed to start llm.invoke span: %s", exc)
        return

    _set_session_and_kind(span, session_id, "llm")

    # Capture the actual prompt as input.value for Phoenix UI
    try:
        input_text = ""
        if isinstance(request_messages, list):
            # Format: [{"role": "user", "content": "..."}, ...]
            parts = []
            for msg in request_messages:
                if isinstance(msg, dict):
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    parts.append(f"[{role}] {content}")
                else:
                    parts.append(str(msg))
            input_text = "\n".join(parts)
        elif isinstance(request_messages, str):
            input_text = request_messages
        elif user_message is not None:
            input_text = str(user_message)
        elif isinstance(request, dict) and "body" in request:
            body = request["body"]
            if isinstance(body, dict) and "messages" in body:
                msgs = body["messages"]
                if isinstance(msgs, list):
                    parts = []
                    for m in msgs:
                        if isinstance(m, dict):
                            parts.append(f"[{m.get('role','?')}] {m.get('content','')}")
                        else:
                            parts.append(str(m))
                    input_text = "\n".join(parts)
        if input_text:
            span.set_attribute("input.value", _safe_serialize(input_text, max_len=8000))
            span.set_attribute("input.mime_type", "text/plain")
    except Exception:
        pass

    with _STATE_LOCK:
        _SPAN_STATE[key] = {
            "span": span,
            "started_at": started_at or time.time(),
            "model": model,
            "provider": provider,
        }

    _debug(f"started llm.invoke span for {key} model={model} provider={provider}")


def on_post_api_request(
    *,
    task_id: str = "",
    turn_id: str = "",
    api_request_id: str = "",
    session_id: str = "",
    platform: str = "",
    model: str = "",
    provider: str = "",
    base_url: str = "",
    api_mode: str = "",
    api_call_count: int = 0,
    api_duration: float = 0.0,
    started_at: float = 0.0,
    ended_at: float = 0.0,
    finish_reason: str = "",
    message_count: int = 0,
    response_model: Optional[str] = None,
    response: Any = None,
    usage: Any = None,
    assistant_message: Any = None,
    assistant_content_chars: int = 0,
    assistant_tool_call_count: int = 0,
    **_: Any,
) -> None:
    """End the ``llm.invoke`` span with usage and response metadata."""
    key = _req_key(api_request_id)

    with _STATE_LOCK:
        state = _SPAN_STATE.pop(key, None)
    if state is None:
        return

    span = state.get("span")
    if span is None:
        return

    try:
        # Usage from the pre-built summary dict
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)
            cache_read = usage.get("cache_read_tokens", 0)
            cache_write = usage.get("cache_write_tokens", 0)
            reasoning = usage.get("reasoning_tokens", 0)

            if input_tokens:
                span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
            if output_tokens:
                span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
            if cache_read:
                span.set_attribute("gen_ai.usage.cache_read_tokens", cache_read)
            if cache_write:
                span.set_attribute("gen_ai.usage.cache_write_tokens", cache_write)
            if reasoning:
                span.set_attribute("gen_ai.usage.reasoning_tokens", reasoning)

        # Finish reason
        if finish_reason:
            span.set_attribute("gen_ai.response.finish_reason", finish_reason)

        # Response model (sometimes different from request model, e.g. routing)
        if response_model:
            span.set_attribute("gen_ai.response.model", response_model)

        # Duration
        if api_duration and api_duration > 0:
            span.set_attribute("hermes.api_duration_s", round(api_duration, 3))

        # Tool calls in response
        if assistant_tool_call_count:
            span.set_attribute("gen_ai.response.tool_call_count", assistant_tool_call_count)

        # Capture the actual assistant response as output.value for Phoenix UI
        try:
            output_text = ""
            if assistant_message is not None:
                if isinstance(assistant_message, dict):
                    output_text = assistant_message.get("content", "")
                    if not output_text and "tool_calls" in assistant_message:
                        tc = assistant_message["tool_calls"]
                        if isinstance(tc, list):
                            output_text = f"[tool_calls] {tc}"
                else:
                    output_text = str(assistant_message)
            elif isinstance(response, dict):
                # Try to extract content from common response shapes
                choices = response.get("choices", [])
                if choices and isinstance(choices, list):
                    first = choices[0]
                    if isinstance(first, dict):
                        msg = first.get("message", {})
                        if isinstance(msg, dict):
                            output_text = msg.get("content", "")
                        else:
                            output_text = str(msg)
                if not output_text:
                    output_text = str(response.get("content", ""))
            if output_text:
                span.set_attribute("output.value", _safe_serialize(output_text, max_len=8000))
                span.set_attribute("output.mime_type", "text/plain")
        except Exception:
            pass

        span.set_status(_Status(_StatusCode.OK))
        span.end()
        _debug(f"ended llm.invoke span for {key} duration={api_duration:.3f}s")
    except Exception as exc:
        logger.debug("phoenix plugin: failed to end llm.invoke span: %s", exc)
        try:
            span.end()
        except Exception:
            pass


def on_pre_tool_call(
    *,
    tool_name: str = "",
    args: Any = None,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    turn_id: str = "",
    api_request_id: str = "",
    middleware_trace: Any = None,
    **_: Any,
) -> Optional[Dict[str, str]]:
    """Start a ``tool.invoke`` span and return TRACEPARENT for propagation.

    When the tool is a subprocess (terminal, Pantheon worker, OpenCode,
    etc.), Hermes passes the returned dict through to the subprocess env.
    We inject ``TRACEPARENT`` here so the child process can attach its
    spans as children of this trace.
    """
    tracer = _get_or_create_tracer()
    key = _tool_key(tool_call_id, tool_name)

    attrs: Dict[str, Any] = {
        "tool.name": tool_name,
        "hermes.task_id": task_id or "",
        "hermes.session_id": session_id or "",
        "hermes.turn_id": turn_id or "",
        "hermes.tool_call_id": tool_call_id or "",
    }

    try:
        safe_args = _safe_serialize(args, max_len=4000)
        if isinstance(safe_args, dict):
            for k, v in safe_args.items():
                attrs[f"tool.arg.{k}"] = v
        else:
            attrs["tool.args_preview"] = str(safe_args)[:4000]
        # Also set as input.value for Phoenix UI
        attrs["input.value"] = str(safe_args)[:8000]
        attrs["input.mime_type"] = "application/json"
    except Exception:
        pass

    try:
        span = tracer.start_span("tool.invoke", kind=_SpanKind.INTERNAL, attributes=attrs)
    except Exception as exc:
        logger.debug("phoenix plugin: failed to start tool.invoke span: %s", exc)
        return None

    _set_session_and_kind(span, session_id, "tool")

    with _STATE_LOCK:
        _SPAN_STATE[key] = {
            "span": span,
            "started_at": time.time(),
            "tool_name": tool_name,
        }

    _debug(f"started tool.invoke span for {key} tool={tool_name}")

    # Build TRACEPARENT for subprocess propagation.
    # Hermes tool-executor will merge this dict into the subprocess env.
    traceparent = get_current_traceparent()
    if traceparent:
        return {"TRACEPARENT": traceparent}
    return None


def on_post_tool_call(
    *,
    tool_name: str = "",
    args: Any = None,
    result: Any = None,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
    turn_id: str = "",
    api_request_id: str = "",
    duration_ms: int = 0,
    status: Optional[str] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    middleware_trace: Any = None,
    **_: Any,
) -> None:
    """End the ``tool.invoke`` span with result metadata."""
    key = _tool_key(tool_call_id, tool_name)

    with _STATE_LOCK:
        state = _SPAN_STATE.pop(key, None)
    if state is None:
        return

    span = state.get("span")
    if span is None:
        return

    try:
        if duration_ms and duration_ms > 0:
            span.set_attribute("tool.duration_ms", duration_ms)

        if status:
            span.set_attribute("tool.status", status)
            if status in {"error", "blocked", "cancelled"}:
                span.set_status(
                    _Status(_StatusCode.ERROR, description=f"{status}: {error_message or ''}")
                )
            else:
                span.set_status(_Status(_StatusCode.OK))
        else:
            span.set_status(_Status(_StatusCode.OK))

        if error_type:
            span.set_attribute("error.type", error_type)
        if error_message:
            span.set_attribute("error.message", str(error_message)[:1000])

        # Result summary (best-effort)
        try:
            if isinstance(result, str):
                span.set_attribute("tool.result.length", len(result))
                if len(result) <= 500:
                    span.set_attribute("tool.result.preview", result)
                else:
                    span.set_attribute("tool.result.preview", result[:500] + "...")
                # Full result as output.value for Phoenix UI
                span.set_attribute("output.value", _safe_serialize(result, max_len=8000))
                span.set_attribute("output.mime_type", "text/plain")
            elif isinstance(result, dict):
                span.set_attribute("tool.result.keys", list(result.keys())[:20])
                if "error" in result:
                    span.set_attribute("tool.result.has_error", True)
                    span.set_attribute("tool.result.error", str(result["error"])[:1000])
                # Full result as output.value for Phoenix UI
                span.set_attribute("output.value", _safe_serialize(result, max_len=8000))
                span.set_attribute("output.mime_type", "application/json")
            else:
                span.set_attribute("output.value", _safe_serialize(str(result), max_len=8000))
                span.set_attribute("output.mime_type", "text/plain")
        except Exception:
            pass

        span.end()
        _debug(f"ended tool.invoke span for {key} status={status} duration_ms={duration_ms}")
    except Exception as exc:
        logger.debug("phoenix plugin: failed to end tool.invoke span: %s", exc)
        try:
            span.end()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────
# Public API helpers (used by other plugins / tools)
# ──────────────────────────────────────────────────────────────────────────

def inject_trace_context(env: Dict[str, str]) -> Dict[str, str]:
    """Public helper: inject current W3C traceparent into *env*.

    Mirrors the Pantheon ``tracing.inject_trace_context`` API so that
    custom tools can propagate trace context to their subprocesses.
    """
    return _inject_traceparent_into_env(env)


# ──────────────────────────────────────────────────────────────────────────
# Plugin registration
# ──────────────────────────────────────────────────────────────────────────

def register(ctx) -> None:
    ctx.register_hook("pre_api_request", on_pre_api_request)
    ctx.register_hook("post_api_request", on_post_api_request)
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    ctx.register_hook("post_tool_call", on_post_tool_call)
    _install_subprocess_patch()


# ──────────────────────────────────────────────────────────────────────────
# Subprocess monkey-patch: inject TRACEPARENT into all child processes
# ──────────────────────────────────────────────────────────────────────────

_SUBPROCESS_PATCHED = False
_ORIGINAL_POPEN: Any = None


def _install_subprocess_patch() -> None:
    """Wrap ``subprocess.Popen`` so every child process receives TRACEPARENT.

    This ensures that tools like ``terminal``, ``delegate_task``, and
    ``opencode`` propagate the active trace context to their subprocesses
    without requiring individual tool modifications.
    """
    global _SUBPROCESS_PATCHED, _ORIGINAL_POPEN
    if _SUBPROCESS_PATCHED:
        return
    try:
        import subprocess

        _ORIGINAL_POPEN = subprocess.Popen

        def _popen_with_traceparent(*args, **kwargs):
            env = kwargs.get("env")
            if env is not None:
                _inject_traceparent_into_env(env)
            else:
                # When env is not provided, subprocess inherits os.environ.
                # We must create a copy and inject TRACEPARENT so we don't
                # mutate the global os.environ dict.
                kwargs["env"] = _inject_traceparent_into_env(dict(os.environ))
            return _ORIGINAL_POPEN(*args, **kwargs)

        subprocess.Popen = _popen_with_traceparent
        _SUBPROCESS_PATCHED = True
        _debug("subprocess.Popen patched for TRACEPARENT propagation")
    except Exception as exc:
        logger.debug("phoenix plugin: could not patch subprocess.Popen: %s", exc)
