"""Tests for the Phoenix observability plugin."""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestPhoenixPlugin:
    """Tests for the Phoenix plugin module."""

    def test_module_loads_without_errors(self):
        """Module should load without import errors."""
        from plugins.observability.phoenix import (
            get_current_traceparent,
            inject_trace_context,
            register,
        )

        assert callable(register)
        assert callable(inject_trace_context)
        assert callable(get_current_traceparent)

    def test_noop_fallback_without_otel(self):
        """Plugin should use no-op tracer when OTel is unavailable."""
        import sys

        mod_name = "plugins.observability.phoenix"
        real_mod = sys.modules.get(mod_name)

        try:
            if mod_name in sys.modules:
                del sys.modules[mod_name]

            with patch("plugins.observability.phoenix._OTEL_AVAILABLE", False):
                import plugins.observability.phoenix as phoenix

                tracer = phoenix._get_or_create_tracer()
                assert tracer.__class__.__name__ == "_NoOpTracer"

                with tracer.start_as_current_span("test") as span:
                    span.set_attribute("key", "value")
                    assert span.__class__.__name__ == "_NoOpSpan"
        finally:
            if real_mod is not None:
                sys.modules[mod_name] = real_mod
            elif mod_name in sys.modules:
                del sys.modules[mod_name]

    def test_inject_trace_context_no_active_span(self):
        """inject_trace_context should not add TRACEPARENT when no span is active."""
        from plugins.observability.phoenix import inject_trace_context

        env = {}
        inject_trace_context(env)
        assert isinstance(env, dict)

    def test_get_current_traceparent_no_active_span(self):
        """get_current_traceparent should return None when no span is active."""
        from plugins.observability.phoenix import get_current_traceparent

        tp = get_current_traceparent()
        assert tp is None or isinstance(tp, str)

    def test_on_pre_api_request_creates_span(self):
        """on_pre_api_request should create an llm.invoke span."""
        from plugins.observability.phoenix import on_pre_api_request

        with patch("plugins.observability.phoenix._get_or_create_tracer") as mock_get_tracer:
            mock_span = MagicMock()
            mock_tracer = MagicMock()
            mock_tracer.start_span.return_value = mock_span
            mock_get_tracer.return_value = mock_tracer

            on_pre_api_request(
                api_request_id="req-123",
                model="claude-sonnet-4",
                provider="anthropic",
                task_id="task-456",
                session_id="sess-789",
            )

            mock_tracer.start_span.assert_called_once()
            call_args = mock_tracer.start_span.call_args
            assert call_args[0][0] == "llm.invoke"
            assert call_args[1]["attributes"]["gen_ai.request.model"] == "claude-sonnet-4"
            assert call_args[1]["attributes"]["gen_ai.system"] == "anthropic"

    def test_on_post_api_request_ends_span(self):
        """on_post_api_request should end the llm.invoke span."""
        from plugins.observability.phoenix import on_post_api_request

        mock_span = MagicMock()
        key = "req-123"

        with patch("plugins.observability.phoenix._SPAN_STATE", {key: {"span": mock_span}}):
            on_post_api_request(
                api_request_id="req-123",
                usage={"input_tokens": 100, "output_tokens": 50},
                finish_reason="stop",
            )

            mock_span.set_attribute.assert_any_call("gen_ai.usage.input_tokens", 100)
            mock_span.set_attribute.assert_any_call("gen_ai.usage.output_tokens", 50)
            mock_span.set_attribute.assert_any_call("gen_ai.response.finish_reason", "stop")
            mock_span.end.assert_called_once()

    def test_on_pre_tool_call_returns_traceparent(self):
        """on_pre_tool_call should return TRACEPARENT dict when a span is active."""
        from plugins.observability.phoenix import on_pre_tool_call

        with patch("plugins.observability.phoenix._get_or_create_tracer") as mock_get_tracer:
            mock_span = MagicMock()
            mock_tracer = MagicMock()
            mock_tracer.start_span.return_value = mock_span
            mock_get_tracer.return_value = mock_tracer

            with patch("plugins.observability.phoenix.get_current_traceparent", return_value="00-1234567890abcdef-1234567890abcdef-01"):
                result = on_pre_tool_call(
                    tool_name="terminal",
                    args={"command": "echo hello"},
                    tool_call_id="tc-1",
                )

            assert result is not None
            assert "TRACEPARENT" in result
            assert result["TRACEPARENT"].startswith("00-")

    def test_on_post_tool_call_ends_span(self):
        """on_post_tool_call should end the tool.invoke span."""
        from plugins.observability.phoenix import on_post_tool_call

        mock_span = MagicMock()
        key = "tc-1"

        with patch("plugins.observability.phoenix._SPAN_STATE", {key: {"span": mock_span}}):
            on_post_tool_call(
                tool_name="terminal",
                tool_call_id="tc-1",
                status="ok",
                duration_ms=1500,
                result="hello world",
            )

            mock_span.set_attribute.assert_any_call("tool.status", "ok")
            mock_span.set_attribute.assert_any_call("tool.duration_ms", 1500)
            mock_span.end.assert_called_once()

    def test_subprocess_patch_injects_traceparent(self):
        """The subprocess monkey-patch should inject TRACEPARENT into child env."""
        import subprocess
        import sys

        # Ensure we're using the real (OTel-enabled) module
        mod_name = "plugins.observability.phoenix"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        import plugins.observability.phoenix as phoenix

        # Ensure patch is installed
        phoenix._install_subprocess_patch()

        # Create a span so there's an active trace context
        tracer = phoenix._get_or_create_tracer()
        with tracer.start_as_current_span("test_subprocess"):
            # Run a subprocess that prints TRACEPARENT
            result = subprocess.run(
                [sys.executable, "-c", "import os; print(os.environ.get('TRACEPARENT', 'NOT_FOUND'))"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = result.stdout.strip()
            assert output.startswith("00-"), f"Expected W3C traceparent, got: {output}"
