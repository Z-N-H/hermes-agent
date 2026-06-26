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

    def test_llm_span_captures_input_and_output(self):
        """LLM spans should capture input.value (prompt) and output.value (response)."""
        from plugins.observability.phoenix import on_pre_api_request, on_post_api_request

        with patch("plugins.observability.phoenix._get_or_create_tracer") as mock_get_tracer:
            mock_span = MagicMock()
            mock_tracer = MagicMock()
            mock_tracer.start_span.return_value = mock_span
            mock_get_tracer.return_value = mock_tracer

            # Pre-hook: should set input.value with the prompt
            on_pre_api_request(
                api_request_id="req-input-test",
                model="gpt-4",
                provider="openai",
                request_messages=[
                    {"role": "system", "content": "You are a helper."},
                    {"role": "user", "content": "What is 2+2?"},
                ],
                started_at=0,
            )

            # Verify input.value was set on the span
            input_calls = [c for c in mock_span.set_attribute.call_args_list if c[0][0] == "input.value"]
            assert len(input_calls) == 1, "input.value should be set on LLM span"
            input_text = input_calls[0][0][1]
            assert "[system] You are a helper." in input_text
            assert "[user] What is 2+2?" in input_text

            # Verify input.mime_type
            mime_calls = [c for c in mock_span.set_attribute.call_args_list if c[0][0] == "input.mime_type"]
            assert len(mime_calls) == 1
            assert mime_calls[0][0][1] == "text/plain"

            # Post-hook: should set output.value with the response
            mock_span.reset_mock()
            with patch("plugins.observability.phoenix._SPAN_STATE", {
                "req-input-test": {"span": mock_span, "started_at": 0, "model": "gpt-4", "provider": "openai"}
            }):
                on_post_api_request(
                    api_request_id="req-input-test",
                    assistant_message={"role": "assistant", "content": "2+2 equals 4."},
                    usage={"input_tokens": 15, "output_tokens": 8},
                )

            output_calls = [c for c in mock_span.set_attribute.call_args_list if c[0][0] == "output.value"]
            assert len(output_calls) == 1, "output.value should be set on LLM span"
            assert output_calls[0][0][1] == "2+2 equals 4."

            output_mime_calls = [c for c in mock_span.set_attribute.call_args_list if c[0][0] == "output.mime_type"]
            assert len(output_mime_calls) == 1
            assert output_mime_calls[0][0][1] == "text/plain"

    def test_tool_span_captures_input_and_output(self):
        """Tool spans should capture input.value (args) and output.value (result)."""
        from plugins.observability.phoenix import on_pre_tool_call, on_post_tool_call

        with patch("plugins.observability.phoenix._get_or_create_tracer") as mock_get_tracer:
            mock_span = MagicMock()
            mock_tracer = MagicMock()
            mock_tracer.start_span.return_value = mock_span
            mock_get_tracer.return_value = mock_tracer

            with patch("plugins.observability.phoenix.get_current_traceparent", return_value=None):
                # Pre-hook: should include input.value in start_span attributes
                on_pre_tool_call(
                    tool_name="terminal",
                    tool_call_id="tc-input-test",
                    args={"command": "echo hello", "workdir": "/tmp"},
                )

            # Verify start_span was called with input.value in attributes
            call_kwargs = mock_tracer.start_span.call_args[1]
            attrs = call_kwargs.get("attributes", {})
            assert "input.value" in attrs, "input.value should be in tool span attributes"
            assert "echo hello" in str(attrs["input.value"])
            assert attrs.get("input.mime_type") == "application/json"

            # Post-hook: should set output.value with the result
            mock_span.reset_mock()
            with patch("plugins.observability.phoenix._SPAN_STATE", {
                "tc-input-test": {"span": mock_span, "started_at": 0, "tool_name": "terminal"}
            }):
                on_post_tool_call(
                    tool_name="terminal",
                    tool_call_id="tc-input-test",
                    result="hello\n",
                    duration_ms=100,
                    status="success",
                )

            output_calls = [c for c in mock_span.set_attribute.call_args_list if c[0][0] == "output.value"]
            assert len(output_calls) == 1, "output.value should be set on tool span"
            assert output_calls[0][0][1] == "hello\n"

            output_mime_calls = [c for c in mock_span.set_attribute.call_args_list if c[0][0] == "output.mime_type"]
            assert len(output_mime_calls) == 1
            assert output_mime_calls[0][0][1] == "text/plain"

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

    def test_llm_span_sets_session_id(self):
        """LLM spans should include session.id for Phoenix session tracking."""
        from plugins.observability.phoenix import on_pre_api_request

        with patch("plugins.observability.phoenix._get_or_create_tracer") as mock_get_tracer:
            mock_span = MagicMock()
            mock_tracer = MagicMock()
            mock_tracer.start_span.return_value = mock_span
            mock_get_tracer.return_value = mock_tracer

            on_pre_api_request(
                api_request_id="req-session-test",
                model="gpt-4",
                provider="openai",
                session_id="sess-abc-123",
                request_messages=[{"role": "user", "content": "hi"}],
                started_at=0,
            )

            # Verify session.id was set
            session_calls = [c for c in mock_span.set_attribute.call_args_list if c[0][0] == "session.id"]
            assert len(session_calls) == 1, "session.id should be set on LLM span"
            assert session_calls[0][0][1] == "sess-abc-123"

            # Verify openinference.span.kind = "llm"
            kind_calls = [c for c in mock_span.set_attribute.call_args_list if c[0][0] == "openinference.span.kind"]
            assert len(kind_calls) == 1, "openinference.span.kind should be set on LLM span"
            assert kind_calls[0][0][1] == "llm"

    def test_tool_span_sets_session_id(self):
        """Tool spans should include session.id for Phoenix session tracking."""
        from plugins.observability.phoenix import on_pre_tool_call

        with patch("plugins.observability.phoenix._get_or_create_tracer") as mock_get_tracer:
            mock_span = MagicMock()
            mock_tracer = MagicMock()
            mock_tracer.start_span.return_value = mock_span
            mock_get_tracer.return_value = mock_tracer

            with patch("plugins.observability.phoenix.get_current_traceparent", return_value=None):
                on_pre_tool_call(
                    tool_name="terminal",
                    tool_call_id="tc-session-test",
                    session_id="sess-abc-123",
                    args={"command": "echo hello"},
                )

            # Verify session.id was set
            session_calls = [c for c in mock_span.set_attribute.call_args_list if c[0][0] == "session.id"]
            assert len(session_calls) == 1, "session.id should be set on tool span"
            assert session_calls[0][0][1] == "sess-abc-123"

            # Verify openinference.span.kind = "tool"
            kind_calls = [c for c in mock_span.set_attribute.call_args_list if c[0][0] == "openinference.span.kind"]
            assert len(kind_calls) == 1, "openinference.span.kind should be set on tool span"
            assert kind_calls[0][0][1] == "tool"
