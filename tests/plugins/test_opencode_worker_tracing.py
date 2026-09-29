"""Tests for opencode_worker's Phoenix tracing bridge (task 012).

Loads THIS REPO's own znh-plugins/opencode_worker/__init__.py — not the
deployed site plugin at /mnt/z/pantheon/.hermes/plugins/opencode_worker/
that test_opencode_worker_herdr.py exercises. That module lives outside
this repo and is unaffected by anything here until a deploy/sync step
copies this file over it.

Run:  uv run pytest tests/plugins/test_opencode_worker_tracing.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_INIT = REPO_ROOT / "znh-plugins" / "opencode_worker" / "__init__.py"

pytestmark = pytest.mark.skipif(
    not PLUGIN_INIT.exists(),
    reason=f"opencode_worker plugin not found at {PLUGIN_INIT}",
)

# Same NDJSON sample used in plugins/observability/phoenix/tests/
# test_phoenix_plugin.py — captured live from `opencode run --format json`
# (OpenCode 1.18.25).
OPENCODE_SAMPLE_NDJSON = """
{"type":"step_start","timestamp":1790616253291,"sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","part":{"id":"prt_0e90bb36600150UbUyqdAxfGnJ","messageID":"msg_0e90ba771001R4HQN6myynWau3","sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","snapshot":"53da05e8154ba7f0d6cc854bc3dc2049f8ca9e34","type":"step-start"}}
{"type":"tool_use","timestamp":1790616253809,"sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","part":{"type":"tool","tool":"read","callID":"read:0","state":{"status":"completed","input":{"filePath":"/tmp/opencode-format-probe/sample.txt"},"output":"<path>/tmp/opencode-format-probe/sample.txt</path>\\n<type>file</type>\\n<content>\\n1: hello world\\n\\n(End of file - total 1 lines)\\n</content>","metadata":{"preview":"hello world","truncated":false,"loaded":[],"display":{"type":"file","path":"/tmp/opencode-format-probe/sample.txt","text":"hello world","lineStart":1,"lineEnd":1,"totalLines":1,"truncated":false}},"title":"sample.txt","time":{"start":1790616253799,"end":1790616253807}},"id":"prt_0e90bb561001DpH8N8dZOWQwe5","sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","messageID":"msg_0e90ba771001R4HQN6myynWau3"}}
{"type":"step_finish","timestamp":1790616253896,"sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","part":{"id":"prt_0e90bb5c30018xGPd1wDSWVDHL","reason":"tool-calls","snapshot":"0fe8fc481e835ea4d1ab540a59fa2a18e4a5ab37","messageID":"msg_0e90ba771001R4HQN6myynWau3","sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","type":"step-finish","tokens":{"total":17105,"input":53,"output":92,"reasoning":0,"cache":{"write":0,"read":16960}},"cost":0.009171}}
{"type":"step_start","timestamp":1790616256896,"sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","part":{"id":"prt_0e90bc17a0011E6qgmih0l0v1b","messageID":"msg_0e90bb5e3001ACFSDjOI6j3ZhP","sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","snapshot":"a2d49b87209477d4bbd845edcf2066aab0f8799d","type":"step-start"}}
{"type":"text","timestamp":1790616257135,"sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","part":{"id":"prt_0e90bc1f2001U956uNfe7W5k9I","messageID":"msg_0e90bb5e3001ACFSDjOI6j3ZhP","sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","type":"text","text":"`sample.txt` contains:\\n\\n```text\\nhello world\\n```","time":{"start":1790616257010,"end":1790616257131}}}
{"type":"step_finish","timestamp":1790616257159,"sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","part":{"id":"prt_0e90bc284001e78g20IQHUsz9z","reason":"stop","snapshot":"f3ad9c9ee8ce1e9a7d7c8878e6452d8b95f19833","messageID":"msg_0e90bb5e3001ACFSDjOI6j3ZhP","sessionID":"ses_f16f45a38ffeEG5l2u2iClVxjl","type":"step-finish","tokens":{"total":17220,"input":17179,"output":41,"reasoning":0,"cache":{"write":0,"read":0}},"cost":0.052152}}
""".strip()


@pytest.fixture
def plugin(monkeypatch):
    """Import this repo's own opencode_worker/__init__.py fresh."""
    name = "_opencode_worker_repo_under_test"
    for key in (name, f"{name}.__init__"):
        monkeypatch.delitem(sys.modules, key, raising=False)
    pkg = types.ModuleType(name)
    pkg.__path__ = [str(PLUGIN_INIT.parent)]
    monkeypatch.setitem(sys.modules, name, pkg)
    spec = importlib.util.spec_from_file_location(
        name, PLUGIN_INIT, submodule_search_locations=[str(PLUGIN_INIT.parent)]
    )
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, mod)
    spec.loader.exec_module(mod)
    for var in ("HERDR_ENV", "HERDR_PANE_ID", "HERDR_SOCKET_PATH", "HERDR_DELEGATE_PANES"):
        monkeypatch.delenv(var, raising=False)
    return mod


class TestFormatJsonFlag:
    def test_cmd_requests_json_format(self, plugin, monkeypatch, tmp_path):
        captured = {}

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        def _fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return _Result()

        monkeypatch.setattr(plugin.subprocess, "run", _fake_run)
        monkeypatch.setattr(plugin, "_resolve_opencode_bin", lambda: None)

        plugin._handle_opencode_delegate({"task": "x", "workdir": str(tmp_path)})

        assert "--format" in captured["cmd"]
        idx = captured["cmd"].index("--format")
        assert captured["cmd"][idx + 1] == "json"


class TestTraceAndReconstruct:
    """_trace_and_reconstruct must never break delegation — always returns
    *some* string, and reconstructs readable text from NDJSON when it can."""

    def test_reconstructs_text_from_real_ndjson(self, plugin):
        result = plugin._trace_and_reconstruct(OPENCODE_SAMPLE_NDJSON)
        assert result == "`sample.txt` contains:\n\n```text\nhello world\n```"

    def test_falls_back_to_raw_stdout_when_not_ndjson(self, plugin):
        """A stub/mocked test double (or a genuinely broken opencode run)
        might hand back plain text instead of NDJSON — must not eat it."""
        raw = "from subprocess"
        assert plugin._trace_and_reconstruct(raw) == raw

    def test_falls_back_to_raw_stdout_on_empty_input(self, plugin):
        assert plugin._trace_and_reconstruct("") == ""

    def test_never_raises_when_phoenix_plugin_is_unimportable(self, plugin, monkeypatch):
        """opencode_worker must keep working even when the phoenix plugin
        can't be imported at all (OTel not installed, module missing,
        whatever) — tracing is strictly best-effort."""
        import builtins

        real_import = builtins.__import__

        def _blocking_import(name, *args, **kwargs):
            if name == "plugins.observability.phoenix":
                raise ImportError("simulated: phoenix plugin unavailable")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_blocking_import):
            result = plugin._trace_and_reconstruct(OPENCODE_SAMPLE_NDJSON)

        assert result == OPENCODE_SAMPLE_NDJSON

    def test_uses_the_current_tool_call_id_to_find_the_parent_span(self, plugin, monkeypatch):
        """Confirms the bridge actually wires tool_call_id through to
        get_span_context_for_tool_call, not just that it doesn't crash."""
        calls = {}

        fake_phoenix = MagicMock()
        fake_phoenix.get_span_context_for_tool_call = MagicMock(
            side_effect=lambda tool_call_id, tool_name: calls.setdefault(
                "get_span_context_for_tool_call", (tool_call_id, tool_name)
            )
        )
        fake_phoenix.record_opencode_run = MagicMock(return_value="reconstructed")

        fake_approval = MagicMock()
        fake_approval.get_current_tool_call_id = MagicMock(return_value="tc-real-id")

        with patch.dict(
            sys.modules,
            {
                "plugins.observability.phoenix": fake_phoenix,
                "tools.approval": fake_approval,
            },
        ):
            result = plugin._trace_and_reconstruct(OPENCODE_SAMPLE_NDJSON)

        assert result == "reconstructed"
        assert calls["get_span_context_for_tool_call"] == ("tc-real-id", "opencode_delegate")
        fake_phoenix.record_opencode_run.assert_called_once()
        assert fake_phoenix.record_opencode_run.call_args[0][0] == OPENCODE_SAMPLE_NDJSON


class TestHandleOpencodeDelegateUsesReconstructedOutput:
    def test_success_path_uses_reconstructed_text(self, plugin, monkeypatch, tmp_path):
        class _Result:
            returncode = 0
            stdout = OPENCODE_SAMPLE_NDJSON
            stderr = ""

        monkeypatch.setattr(plugin.subprocess, "run", lambda *a, **k: _Result())
        monkeypatch.setattr(plugin, "_resolve_opencode_bin", lambda: None)
        monkeypatch.setattr(
            plugin, "_trace_and_reconstruct", lambda raw: "reconstructed output"
        )

        out = json.loads(
            plugin._handle_opencode_delegate({"task": "x", "workdir": str(tmp_path)})
        )
        assert out["output"] == "reconstructed output"

    def test_error_path_also_uses_reconstructed_text(self, plugin, monkeypatch, tmp_path):
        class _Result:
            returncode = 1
            stdout = OPENCODE_SAMPLE_NDJSON
            stderr = "boom"

        monkeypatch.setattr(plugin.subprocess, "run", lambda *a, **k: _Result())
        monkeypatch.setattr(plugin, "_resolve_opencode_bin", lambda: None)
        monkeypatch.setattr(
            plugin, "_trace_and_reconstruct", lambda raw: "reconstructed output"
        )

        out = json.loads(
            plugin._handle_opencode_delegate({"task": "x", "workdir": str(tmp_path)})
        )
        assert out["error"] == "OpenCode exited 1"
        assert out["stdout"] == "reconstructed output"
