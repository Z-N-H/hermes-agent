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

    def test_on_api_request_error_ends_span_and_clears_state(self):
        """on_api_request_error should end the llm.invoke span and clear _SPAN_STATE.

        Without this, a request that errors instead of completing (network
        failure, sandbox block, invalid response) leaves its span in
        _SPAN_STATE forever, since on_post_api_request only fires on success.
        """
        from plugins.observability.phoenix import on_api_request_error

        mock_span = MagicMock()
        key = "req-123"

        with patch("plugins.observability.phoenix._SPAN_STATE", {key: {"span": mock_span}}) as state:
            on_api_request_error(
                api_request_id="req-123",
                error_type="ConnectionResetError",
                error_message="Connection reset by peer",
            )

            mock_span.set_attribute.assert_any_call("error.type", "ConnectionResetError")
            mock_span.end.assert_called_once()
            assert key not in state

    def test_on_api_request_error_missing_key_is_noop(self):
        """Unknown api_request_id should not raise (e.g. hook fired without a matching pre_api_request)."""
        from plugins.observability.phoenix import on_api_request_error

        with patch("plugins.observability.phoenix._SPAN_STATE", {}):
            on_api_request_error(api_request_id="unknown-req", error_type="Timeout")

    def test_register_wires_api_request_error_hook(self):
        """register() must subscribe on_api_request_error, or failed requests leak spans forever."""
        from plugins.observability.phoenix import register

        ctx = MagicMock()
        register(ctx)

        hook_names = [call.args[0] for call in ctx.register_hook.call_args_list]
        assert "api_request_error" in hook_names

    def test_on_pre_tool_call_returns_traceparent(self):
        """on_pre_tool_call should return a TRACEPARENT dict actually rooted
        in the tool.invoke span it just created — not in ambient/"current"
        context, which this plugin's spans are never attached to. Uses a
        real OTel SDK tracer (not a mock span) because the previous version
        of this test only proved get_current_traceparent()'s return value
        was plumbed through, which is exactly the ambient-context bug this
        fix removes — a MagicMock span can't prove the traceparent is
        rooted in the right span, only a real one with a decodable
        SpanContext can."""
        import plugins.observability.phoenix as phoenix
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.trace import format_span_id, format_trace_id

        provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
        tracer = provider.get_tracer("test")

        with patch.object(phoenix, "_TRACER", tracer), patch.object(phoenix, "_SPAN_STATE", {}):
            result = phoenix.on_pre_tool_call(
                tool_name="terminal",
                args={"command": "echo hello"},
                tool_call_id="tc-1",
            )

            assert result is not None
            assert "TRACEPARENT" in result
            traceparent = result["TRACEPARENT"]
            assert traceparent.startswith("00-")

            span = phoenix._SPAN_STATE["tc-1"]["span"]
            span_ctx = span.get_span_context()
            expected = f"00-{format_trace_id(span_ctx.trace_id)}-{format_span_id(span_ctx.span_id)}-01"
            assert traceparent == expected, (
                f"TRACEPARENT must be rooted in the tool.invoke span itself: "
                f"expected {expected}, got {traceparent}"
            )

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


class TestPhoenixTurnParenting:
    """Integration tests: spans from the same turn must share one trace.

    Uses a real OTel SDK tracer bound to an in-memory exporter (not mocks)
    so trace_id/parent span_id come from actual OTel context propagation,
    not from asserting call_args shapes.
    """

    def _fresh_tracer(self):
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        exporter = InMemorySpanExporter()
        provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        return provider.get_tracer("test"), exporter

    def setup_method(self):
        import plugins.observability.phoenix as phoenix

        self.phoenix = phoenix
        tracer, exporter = self._fresh_tracer()
        self.exporter = exporter
        self._patches = [
            patch.object(phoenix, "_TRACER", tracer),
            patch.object(phoenix, "_SPAN_STATE", {}),
            patch.object(phoenix, "_TURN_SPANS", {}),
            patch.object(phoenix, "_SESSION_CURRENT_TURN", {}),
        ]
        for p in self._patches:
            p.start()

    def teardown_method(self):
        for p in self._patches:
            p.stop()

    def test_llm_and_tool_spans_in_same_turn_share_one_trace(self):
        """llm.invoke -> tool.invoke -> llm.invoke within one turn_id must
        all land in a single trace, parented under that turn's root span —
        not three disconnected single-span traces."""
        phoenix = self.phoenix

        phoenix.on_pre_api_request(
            api_request_id="req-1", session_id="sess-1", turn_id="turn-1",
            model="m", provider="p",
        )
        phoenix.on_post_api_request(api_request_id="req-1", usage={"input_tokens": 1})

        phoenix.on_pre_tool_call(
            tool_name="terminal", tool_call_id="tc-1", session_id="sess-1", turn_id="turn-1",
        )
        phoenix.on_post_tool_call(tool_name="terminal", tool_call_id="tc-1", status="ok")

        phoenix.on_pre_api_request(
            api_request_id="req-2", session_id="sess-1", turn_id="turn-1",
            model="m", provider="p",
        )
        phoenix.on_post_api_request(api_request_id="req-2", usage={"input_tokens": 1})

        # End the turn explicitly (as on_session_end would) so its root span
        # is exported alongside the children.
        phoenix._flush_session_turn(session_id="sess-1")

        spans = self.exporter.get_finished_spans()
        names = sorted(s.name for s in spans)
        assert names == ["llm.invoke", "llm.invoke", "tool.invoke", "turn"]

        trace_ids = {s.context.trace_id for s in spans}
        assert len(trace_ids) == 1, f"expected one shared trace, got {len(trace_ids)}: {spans}"

        turn_span = next(s for s in spans if s.name == "turn")
        for s in spans:
            if s.name == "turn":
                continue
            assert s.parent is not None
            assert s.parent.span_id == turn_span.context.span_id, (
                f"{s.name} should be parented under the turn span"
            )

    def test_new_turn_id_closes_previous_turn_span(self):
        """A turn_id change for the same session must close the previous
        turn's root span and start a new trace for the next one."""
        phoenix = self.phoenix

        phoenix.on_pre_api_request(
            api_request_id="req-1", session_id="sess-1", turn_id="turn-1", model="m", provider="p",
        )
        phoenix.on_post_api_request(api_request_id="req-1", usage={"input_tokens": 1})

        phoenix.on_pre_api_request(
            api_request_id="req-2", session_id="sess-1", turn_id="turn-2", model="m", provider="p",
        )
        phoenix.on_post_api_request(api_request_id="req-2", usage={"input_tokens": 1})

        phoenix._flush_session_turn(session_id="sess-1")

        spans = self.exporter.get_finished_spans()
        turn_spans = [s for s in spans if s.name == "turn"]
        assert len(turn_spans) == 2, "each turn_id should get its own root span"

        trace_ids = {s.context.trace_id for s in turn_spans}
        assert len(trace_ids) == 2, "different turns must not share a trace"

    def test_session_end_flushes_open_turn(self):
        """on_session_end (wired via _flush_session_turn) must end whatever
        turn is still open, so its root span isn't left dangling/unflushed."""
        phoenix = self.phoenix

        phoenix.on_pre_api_request(
            api_request_id="req-1", session_id="sess-1", turn_id="turn-1", model="m", provider="p",
        )
        phoenix.on_post_api_request(api_request_id="req-1", usage={"input_tokens": 1})

        assert "sess-1" in phoenix._SESSION_CURRENT_TURN
        assert self.exporter.get_finished_spans() == () or all(
            s.name != "turn" for s in self.exporter.get_finished_spans()
        )

        phoenix._flush_session_turn(session_id="sess-1")

        assert "sess-1" not in phoenix._SESSION_CURRENT_TURN
        assert "turn-1" not in phoenix._TURN_SPANS
        assert any(s.name == "turn" for s in self.exporter.get_finished_spans())

    def test_register_wires_session_end_hooks(self):
        """register() must subscribe the turn-flush handler to every session
        lifecycle hook, or a turn's root span outlives its session."""
        from plugins.observability.phoenix import register

        ctx = MagicMock()
        register(ctx)

        hook_names = [call.args[0] for call in ctx.register_hook.call_args_list]
        assert "on_session_end" in hook_names
        assert "on_session_finalize" in hook_names
        assert "on_session_reset" in hook_names


class TestPhoenixToolCallSpanContext:
    """get_span_context_for_tool_call() must hand back the real tool.invoke
    span's context, so in-process callers (e.g. a tool implementation
    replaying a subprocess's own structured output as spans) can parent
    child spans under the exact tool call, not the turn or nothing at all."""

    def _fresh_tracer(self):
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        exporter = InMemorySpanExporter()
        provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        return provider.get_tracer("test"), exporter

    def setup_method(self):
        import plugins.observability.phoenix as phoenix

        self.phoenix = phoenix
        tracer, exporter = self._fresh_tracer()
        self.exporter = exporter
        self._patches = [
            patch.object(phoenix, "_TRACER", tracer),
            patch.object(phoenix, "_SPAN_STATE", {}),
            patch.object(phoenix, "_TURN_SPANS", {}),
            patch.object(phoenix, "_SESSION_CURRENT_TURN", {}),
        ]
        for p in self._patches:
            p.start()

    def teardown_method(self):
        for p in self._patches:
            p.stop()

    def test_child_span_parents_under_the_tool_call_not_the_turn(self):
        phoenix = self.phoenix

        phoenix.on_pre_tool_call(
            tool_name="opencode", tool_call_id="tc-1", session_id="sess-1", turn_id="turn-1",
        )

        context = phoenix.get_span_context_for_tool_call("tc-1", "opencode")
        assert context is not None

        child = phoenix._TRACER.start_span("opencode.step", context=context)
        child.end()

        phoenix.on_post_tool_call(tool_name="opencode", tool_call_id="tc-1", status="ok")
        phoenix._flush_session_turn(session_id="sess-1")

        spans = self.exporter.get_finished_spans()
        names = sorted(s.name for s in spans)
        assert names == ["opencode.step", "tool.invoke", "turn"]

        trace_ids = {s.context.trace_id for s in spans}
        assert len(trace_ids) == 1, "child span must share the tool call's trace"

        tool_span = next(s for s in spans if s.name == "tool.invoke")
        child_span = next(s for s in spans if s.name == "opencode.step")
        assert child_span.parent is not None
        assert child_span.parent.span_id == tool_span.context.span_id, (
            "child span must be parented under the tool.invoke span, not the turn span"
        )

    def test_returns_none_for_unknown_tool_call(self):
        phoenix = self.phoenix
        assert phoenix.get_span_context_for_tool_call("no-such-id", "opencode") is None

    def test_returns_none_after_tool_call_already_ended(self):
        phoenix = self.phoenix

        phoenix.on_pre_tool_call(tool_name="opencode", tool_call_id="tc-2")
        phoenix.on_post_tool_call(tool_name="opencode", tool_call_id="tc-2", status="ok")

        assert phoenix.get_span_context_for_tool_call("tc-2", "opencode") is None


# Captured live from `opencode run --format json` (OpenCode 1.18.25),
# `opencode run --format json "read the file sample.txt in this directory
# and tell me its contents"` against a one-line sample.txt. Undocumented
# event shape — see record_opencode_run's docstring. Two steps: one
# tool-calling step (reads the file) and one text-only step (reports back).
OPENCODE_SAMPLE_NDJSON = """
{"type":"step_start","timestamp":1790616253291,"sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","part":{"id":"prt_0e90bb36600150UbUyqdAxfGnJ","messageID":"msg_0e90ba771001R4HQN6myynWau3","sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","snapshot":"53da05e8154ba7f0d6cc854bc3dc2049f8ca9e34","type":"step-start"}}
{"type":"tool_use","timestamp":1790616253809,"sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","part":{"type":"tool","tool":"read","callID":"read:0","state":{"status":"completed","input":{"filePath":"/tmp/opencode-format-probe/sample.txt"},"output":"<path>/tmp/opencode-format-probe/sample.txt</path>\\n<type>file</type>\\n<content>\\n1: hello world\\n\\n(End of file - total 1 lines)\\n</content>","metadata":{"preview":"hello world","truncated":false,"loaded":[],"display":{"type":"file","path":"/tmp/opencode-format-probe/sample.txt","text":"hello world","lineStart":1,"lineEnd":1,"totalLines":1,"truncated":false}},"title":"sample.txt","time":{"start":1790616253799,"end":1790616253807}},"id":"prt_0e90bb561001DpH8N8dZOWQwe5","sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","messageID":"msg_0e90ba771001R4HQN6myynWau3"}}
{"type":"step_finish","timestamp":1790616253896,"sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","part":{"id":"prt_0e90bb5c30018xGPd1wDSWVDHL","reason":"tool-calls","snapshot":"0fe8fc481e835ea4d1ab540a59fa2a18e4a5ab37","messageID":"msg_0e90ba771001R4HQN6myynWau3","sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","type":"step-finish","tokens":{"total":17105,"input":53,"output":92,"reasoning":0,"cache":{"write":0,"read":16960}},"cost":0.009171}}
{"type":"step_start","timestamp":1790616256896,"sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","part":{"id":"prt_0e90bc17a0011E6qgmih0l0v1b","messageID":"msg_0e90bb5e3001ACFSDjOI6j3ZhP","sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","snapshot":"a2d49b87209477d4bbd845edcf2066aab0f8799d","type":"step-start"}}
{"type":"text","timestamp":1790616257135,"sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","part":{"id":"prt_0e90bc1f2001U956uNfe7W5k9I","messageID":"msg_0e90bb5e3001ACFSDjOI6j3ZhP","sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","type":"text","text":"`sample.txt` contains:\\n\\n```text\\nhello world\\n```","time":{"start":1790616257010,"end":1790616257131}}}
{"type":"step_finish","timestamp":1790616257159,"sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","part":{"id":"prt_0e90bc284001e78g20IQHUsz9z","reason":"stop","snapshot":"f3ad9c9ee8ce1e9a7d7c8878e6452d8b95f19833","messageID":"msg_0e90bb5e3001ACFSDjOI6j3ZhP","sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","type":"step-finish","tokens":{"total":17220,"input":17179,"output":41,"reasoning":0,"cache":{"write":0,"read":0}},"cost":0.052152}}
""".strip()


class TestRecordOpencodeRun:
    """record_opencode_run() parses opencode run --format json NDJSON,
    emits spans nested under the delegating tool call, and returns
    reconstructed text for the agent to see in place of raw NDJSON."""

    def _fresh_tracer(self):
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        exporter = InMemorySpanExporter()
        provider = TracerProvider(resource=Resource.create({"service.name": "test"}))
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        return provider.get_tracer("test"), exporter

    def setup_method(self):
        import plugins.observability.phoenix as phoenix

        self.phoenix = phoenix
        tracer, exporter = self._fresh_tracer()
        self.exporter = exporter
        self._patches = [
            patch.object(phoenix, "_TRACER", tracer),
            patch.object(phoenix, "_SPAN_STATE", {}),
        ]
        for p in self._patches:
            p.start()

    def teardown_method(self):
        for p in self._patches:
            p.stop()

    def test_reconstructs_final_text(self):
        text = self.phoenix.record_opencode_run(OPENCODE_SAMPLE_NDJSON, None)
        # Verified live: `opencode run` (--format default) against the same
        # prompt/file printed exactly the second step's text with no
        # extra wrapping — record_opencode_run must reproduce that, not
        # dump raw NDJSON or add its own formatting.
        assert text == "`sample.txt` contains:\n\n```text\nhello world\n```"

    def test_emits_one_step_span_per_message_id_plus_one_tool_span(self):
        self.phoenix.record_opencode_run(OPENCODE_SAMPLE_NDJSON, None)

        spans = self.exporter.get_finished_spans()
        names = sorted(s.name for s in spans)
        assert names == ["opencode.llm.invoke", "opencode.llm.invoke", "opencode.tool.read"]

    def test_tool_span_nests_under_its_own_step_not_the_other_step(self):
        self.phoenix.record_opencode_run(OPENCODE_SAMPLE_NDJSON, None)

        spans = self.exporter.get_finished_spans()
        tool_span = next(s for s in spans if s.name == "opencode.tool.read")
        step_spans = [s for s in spans if s.name == "opencode.llm.invoke"]
        tool_calling_step = next(s for s in step_spans if "tool-calls" in str(s.attributes.get("opencode.reason")))

        assert tool_span.parent is not None
        assert tool_span.parent.span_id == tool_calling_step.context.span_id
        assert tool_span.context.trace_id == tool_calling_step.context.trace_id

    def test_step_spans_carry_token_and_cost_data(self):
        self.phoenix.record_opencode_run(OPENCODE_SAMPLE_NDJSON, None)

        spans = self.exporter.get_finished_spans()
        step_spans = [s for s in spans if s.name == "opencode.llm.invoke"]
        text_step = next(s for s in step_spans if s.attributes.get("opencode.reason") == "stop")

        assert text_step.attributes["gen_ai.usage.input_tokens"] == 17179
        assert text_step.attributes["gen_ai.usage.output_tokens"] == 41
        assert text_step.attributes["opencode.cost_usd"] == pytest.approx(0.052152)
        assert text_step.attributes["gen_ai.system"] == "opencode"

    def test_tool_span_carries_input_and_output(self):
        self.phoenix.record_opencode_run(OPENCODE_SAMPLE_NDJSON, None)

        spans = self.exporter.get_finished_spans()
        tool_span = next(s for s in spans if s.name == "opencode.tool.read")

        assert tool_span.attributes["tool.name"] == "read"
        assert tool_span.attributes["tool.status"] == "completed"
        assert "sample.txt" in tool_span.attributes["input.value"]
        assert "hello world" in tool_span.attributes["output.value"]

    def test_spans_nest_under_explicit_parent_context(self):
        """When given a parent_context (the delegating tool.invoke span's
        context), all opencode spans must share its trace — proving the
        bridge actually closes the loop between hermes's tool call and
        OpenCode's own activity, not just producing orphaned spans."""
        phoenix = self.phoenix

        phoenix.on_pre_tool_call(tool_name="opencode_delegate", tool_call_id="tc-bridge")
        parent_context = phoenix.get_span_context_for_tool_call("tc-bridge", "opencode_delegate")
        assert parent_context is not None

        phoenix.record_opencode_run(OPENCODE_SAMPLE_NDJSON, parent_context)
        phoenix.on_post_tool_call(tool_name="opencode_delegate", tool_call_id="tc-bridge", status="ok")

        spans = self.exporter.get_finished_spans()
        trace_ids = {s.context.trace_id for s in spans}
        assert len(trace_ids) == 1, "opencode spans must share the delegating tool call's trace"

        delegate_span = next(s for s in spans if s.name == "tool.invoke")
        step_spans = [s for s in spans if s.name == "opencode.llm.invoke"]
        assert all(s.parent is not None and s.parent.span_id == delegate_span.context.span_id for s in step_spans), (
            "opencode.llm.invoke steps must be direct children of the delegating tool.invoke span"
        )

    def test_empty_input_returns_empty_string(self):
        assert self.phoenix.record_opencode_run("", None) == ""
        assert self.phoenix.record_opencode_run("   \n  ", None) == ""

    def test_malformed_json_lines_are_skipped_not_fatal(self):
        garbage = "not json at all\n" + OPENCODE_SAMPLE_NDJSON + "\nalso not json{{{"
        text = self.phoenix.record_opencode_run(garbage, None)
        assert text == "`sample.txt` contains:\n\n```text\nhello world\n```"

    def test_totally_unparseable_input_returns_empty_string_not_raw_text(self):
        text = self.phoenix.record_opencode_run("this is not ndjson\nneither is this", None)
        assert text == ""
