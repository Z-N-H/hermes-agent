"""Unit tests for the herdr_bridge Hermes plugin's tool-call surfacing.

The property under test: pre_tool_call's kwargs (tool_name + args, per
hermes-agent's invoke_hook) must fold the current tool and its primary file
into the pane's state label, composing with the subagent aggregate and
reverting on post_tool_call — while an outstanding approval always wins.

Sockets are mocked (module._send is swapped for a capture list), so no herdr
server is needed.

Run:  uvx pytest plugins/herdr_bridge/tests -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parent.parent / "__init__.py"


@pytest.fixture()
def bridge(monkeypatch):
    """Fresh herdr_bridge module with every send captured."""
    return _make_bridge(monkeypatch)


def _make_bridge(monkeypatch, agent_name: str = ""):
    monkeypatch.delitem(sys.modules, "herdr_bridge", raising=False)
    monkeypatch.delitem(sys.modules, "herdr_bridge.__init__", raising=False)
    if agent_name:
        monkeypatch.setenv("HERDR_AGENT_NAME", agent_name)
    else:
        monkeypatch.delenv("HERDR_AGENT_NAME", raising=False)
    spec = importlib.util.spec_from_file_location("herdr_bridge", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sent: list = []
    monkeypatch.setattr(
        mod, "_send",
        lambda method, params, **kw: sent.append((method, dict(params), kw)))
    monkeypatch.setitem(sys.modules, "herdr_bridge", mod)
    return mod, sent


def _last_metadata(sent: list) -> dict:
    return next(p for m, p, _ in reversed(sent) if m == "pane.report_metadata")


def _last_agent(sent: list) -> dict:
    return next(p for m, p, _ in reversed(sent) if m == "pane.report_agent")


def test_file_tool_surfaces_name_and_basename(bridge):
    mod, sent = bridge
    mod.pre_tool_call(tool_name="patch",
                      args={"path": "/deep/vault_kanban_dispatch.py"})
    agent = _last_agent(sent)
    assert agent["state"] == "working"
    assert agent["message"] == "Edit vault_kanban_dispatch.py"
    meta = _last_metadata(sent)
    assert meta["state_labels"] == {"working": "Edit vault_kanban_dispatch.py"}
    # A lone tool label does not claim extra display agent rows.
    assert meta["clear_display_agent"] is True


def test_terminal_tool_surfaces_the_command(bridge):
    mod, sent = bridge
    mod.pre_tool_call(tool_name="terminal",
                      args={"command": "uv run pytest tests/"})
    assert _last_metadata(sent)["state_labels"] == {
        "working": "Run uv run pytest tests/"
    }


def test_unknown_tool_falls_back_to_its_name(bridge):
    mod, sent = bridge
    mod.pre_tool_call(tool_name="web_search", args={"query": "herdr ttl"})
    assert _last_metadata(sent)["state_labels"] == {
        "working": "web_search"
    }


def test_label_reverts_on_post_tool_call(bridge):
    mod, sent = bridge
    mod.pre_tool_call(tool_name="read_file", args={"path": "a.py"})
    mod.post_tool_call(tool_name="read_file", args={"path": "a.py"},
                       status="ok")
    meta = _last_metadata(sent)
    assert meta["clear_state_labels"] is True
    assert _last_agent(sent) == {"state": "working"}  # still mid-turn


def test_tool_label_composes_with_subagents(bridge):
    mod, sent = bridge
    mod.subagent_start(child_session_id="c1", name="writer")
    mod.subagent_start(child_session_id="c2", name="research")
    mod.pre_tool_call(tool_name="write_file", args={"path": "report.md"})
    meta = _last_metadata(sent)
    assert meta["display_agent"] == "hermes (2 subs)"
    assert meta["state_labels"] == {
        "working": "Write report.md · 2 subagents: research, writer"
    }


def test_approval_wins_over_a_tool_label(bridge):
    mod, sent = bridge
    mod.pre_tool_call(tool_name="write_file", args={"path": "x.py"})
    mod.pre_approval_request(command="write_file x.py")
    agent = _last_agent(sent)
    assert agent["state"] == "blocked"
    assert agent["message"].startswith("awaiting approval")
    # ...and an answered approval reveals the still-running tool again.
    mod.post_approval_response(choice="once")
    assert _last_agent(sent)["state"] == "working"
    assert _last_metadata(sent)["state_labels"] == {"working": "Write x.py"}


def test_hook_without_tool_name_keeps_the_label(bridge):
    """A malformed pre_tool_call must not blank the current activity."""
    mod, sent = bridge
    mod.pre_tool_call(tool_name="patch", args={"path": "y.py"})
    mod.pre_tool_call(args={})  # no tool_name: keep what we had
    assert _last_metadata(sent)["state_labels"] == {"working": "Edit y.py"}


# --- subagent child panes ----------------------------------------------------


def _scheme_bridge(monkeypatch, agent_name="cg6w3sa6f-hermes-00"):
    """A bridge inside a dispatcher-named pane, with herdr CLI stubbed."""
    mod, sent = _make_bridge(monkeypatch, agent_name=agent_name)
    monkeypatch.setattr(mod, "_target", lambda: ("w1:p2", "/sock"))
    cli_calls: list = []

    def _fake_cli(*args):
        cli_calls.append(args)
        if args[:2] == ("pane", "split"):
            return {"result": {"pane": {"pane_id": f"w1:p{10 + len(cli_calls)}"}}}
        if args[:2] == ("agent", "list"):
            taken = [c[3] for c in cli_calls if c[:2] == ("agent", "rename")]
            return {"result": {"agents": [{"name": n} for n in taken]}}
        return {"ok": True}

    monkeypatch.setattr(mod, "_cli", _fake_cli)
    return mod, sent, cli_calls


def test_env_agent_name_wins(monkeypatch):
    """The scheme name must replace the stock 'hermes' label or the pane's
    record drops every report this plugin makes (verified live on 0.8.0)."""
    mod, _ = _make_bridge(monkeypatch, agent_name="cg6w3sa6f-hermes-00")
    assert mod.AGENT == "cg6w3sa6f-hermes-00"
    assert mod._child_prefix() == "cg6w3sa6f"


def test_subagent_gets_a_split_pane_on_the_scheme(monkeypatch):
    mod, sent, cli_calls = _scheme_bridge(monkeypatch)
    mod.subagent_start(child_session_id="c1", name="copy-writer")

    assert ("pane", "split", "w1:p2", "--direction", "down",
            "--no-focus") in cli_calls
    rename = next(c for c in cli_calls if c[:2] == ("agent", "rename"))
    assert rename[3] == "cg6w3sa6f-hermes-01"
    # The child reports working onto ITS OWN pane with ITS OWN name...
    child_agent = next(p for m, p, kw in sent
                       if m == "pane.report_agent")
    assert child_agent["state"] == "working"
    child_kw = next(kw for m, _, kw in sent if m == "pane.report_agent")
    assert child_kw["pane_id"].startswith("w1:p1")
    assert child_kw["agent"] == "cg6w3sa6f-hermes-01"
    # ...and stays OUT of the parent's fold.
    assert mod._subagents == {}

    mod.subagent_stop(child_session_id="c1")
    stops = [(p, kw) for m, p, kw in sent if m == "pane.report_agent"
             and p.get("state") == "idle"]
    assert stops and stops[-1][1]["agent"] == "cg6w3sa6f-hermes-01"


def test_subagent_ordinals_skip_taken_names(monkeypatch):
    mod, sent, cli_calls = _scheme_bridge(monkeypatch)
    mod.subagent_start(child_session_id="c1", name="one")
    mod.subagent_start(child_session_id="c2", name="two")
    renames = [c[3] for c in cli_calls if c[:2] == ("agent", "rename")]
    assert renames == ["cg6w3sa6f-hermes-01", "cg6w3sa6f-hermes-02"]


def test_subagent_folds_when_off_the_scheme(monkeypatch):
    """Interactive hermes (plain AGENT='hermes'): the old fold, no panes."""
    mod, sent = _make_bridge(monkeypatch)  # no HERDR_AGENT_NAME
    monkeypatch.setattr(mod, "_target", lambda: ("w1:p2", "/sock"))
    cli_calls: list = []
    monkeypatch.setattr(mod, "_cli",
                        lambda *a: cli_calls.append(a) or {"ok": True})
    mod.subagent_start(child_session_id="c1", name="writer")
    assert cli_calls == []
    assert mod._subagents == {"c1": "writer"}
    meta = _last_metadata(sent)
    assert meta["display_agent"] == "hermes (1 sub)"


def test_split_failure_falls_back_to_the_fold(monkeypatch):
    mod, sent, cli_calls = _scheme_bridge(monkeypatch)
    monkeypatch.setattr(mod, "_cli", lambda *a: None)  # herdr is hiccuping
    mod.subagent_start(child_session_id="c1", name="writer")
    assert mod._subagents == {"c1": "writer"}
    assert mod._child_panes == {}


def test_session_end_flips_leftover_child_panes(monkeypatch):
    mod, sent, cli_calls = _scheme_bridge(monkeypatch)
    mod.subagent_start(child_session_id="c1", name="orphan")
    sent.clear()
    mod.on_session_end()
    idle = [(p, kw) for m, p, kw in sent if m == "pane.report_agent"
            and p.get("state") == "idle"]
    assert idle and idle[0][1]["agent"] == "cg6w3sa6f-hermes-01"
    assert mod._child_panes == {}
