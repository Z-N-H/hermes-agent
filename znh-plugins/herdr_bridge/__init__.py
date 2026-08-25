"""Herdr Bridge — report real Hermes lifecycle state to the enclosing Herdr pane.

Herdr ships its own `herdr-agent-state` plugin, but that one is 91 lines and
registers only `on_session_start`, `on_session_reset` and `pre_llm_call`, all
of which call `pane.report_agent_session` -- session identity, so a pane can be
restored with `--resume`. It never calls `pane.report_agent`, so it emits no
state at all. Herdr's v0.8.0 notes say as much: "Hermes state now derives from
screen detection rather than incomplete hooks."

Screen detection is a bad fit at both ends of how Hermes runs. The interactive
REPL is a full-screen prompt_toolkit Application doing constant redraws, so
turn boundaries aren't recoverable from scrollback; and the dispatcher's
`chat -q -Q` path deliberately nulls the stream callbacks to keep stdout
machine-readable, leaving almost nothing on screen to detect. Either way the
pane sits at `unknown`.

This plugin reports state directly instead, over the same unix socket and wire
format the stock plugin uses. The payoff that matters most: `pre_approval_request`
fires the moment a permission prompt appears, so the pane goes `blocked`
immediately. Headless `-q` runs otherwise block for `approvals.timeout`
(default 300s) and then deny -- silently, with nobody watching. Now it shows
up at once and you can `herdr agent attach` and answer it.

`delegate_task` subagents are promoted to split panes in the parent's tab
(on the opencode_worker pattern): each gets its own agent record named on
the dispatch scheme — `<prefix>-hermes-NN` behind the parent's
`<prefix>-hermes-00`, both derived from the HERDR_AGENT_NAME the dispatcher
injected — reported `working` on subagent_start and flipped to `done` on
subagent_stop, so parent and child report independently and the child's row
stays visible for review until the tab is reaped. The pane is display-only
(the subagent is an in-process thread, not a process), so it gets a banner
describing what it represents instead of a shell doing nothing. When the
parent has no scheme name (interactive use, or a pre-scheme dispatcher) or a
split fails, the old behaviour is preserved: subagents fold into the
parent's state, blocked > working > idle, detail in the report `message`.

`pre_approval_request` still wins over everything: an outstanding approval
masks every tool label and every subagent row on the parent pane.

`pre_tool_call` additionally surfaces what the agent is doing *right now*:
the tool and its primary file path (`patch` -> `Edit vault_kanban_dispatch.py`,
`terminal` -> `Run <command>`) fold into the same state label, composed with
-- never replacing -- the subagent aggregate, and always masked by an
outstanding approval. The label reverts on `post_tool_call`.

Outside a Herdr pane every send is a no-op, so this is safe to leave enabled
everywhere.
"""

from __future__ import annotations

import json
import os
import random
import re
import socket
import subprocess
import threading
import time
from typing import Any

SOURCE = "herdr-bridge:hermes"
# The pane's agent record anchors on the first label it is reported with and
# drops reports from mismatched integration labels (verified live on 0.8.0).
# Dispatched panes are renamed to the scheme (`c<card>-hermes-00`) and carry
# it in HERDR_AGENT_NAME, so we must report under that exact name or every
# state update — including the approval signal — is discarded. Outside the
# scheme the stock-plugin label keeps state and session identity on one
# record rather than fighting over the pane's single slot.
AGENT = os.environ.get("HERDR_AGENT_NAME", "").strip() or "hermes"
HERDR_BIN = os.environ.get("HERDR_BIN", "/home/znh/.local/bin/herdr")

_SEND_TIMEOUT = 0.5
_MESSAGE_MAX = 200

_lock = threading.Lock()
_subagents: dict[str, str] = {}
# key -> (pane_id, agent name) for subagents promoted to their own pane;
# such a subagent stays OUT of the _subagents fold because it has its own row.
_child_panes: dict[str, tuple[str, str]] = {}
_approval: str | None = None
_tool: str | None = None
_busy = False
_session_id: str | None = None
_last: tuple[str, str] | None = None
_seq = time.time_ns()

_SCHEME_NAME_RE = re.compile(r"^([ct][a-z0-9]+)-(?:opencode|hermes)-\d{2}$")

# Display verbs for the tools Hermes actually exposes (arg conventions
# verified against hermes-agent's tool schemas: file tools take `path`,
# terminal takes `command`). Unknown tools fall through to their raw name.
_TOOL_VERBS = {
    "read_file": "Read",
    "write_file": "Write",
    "patch": "Edit",
    "edit_file": "Edit",
    "terminal": "Run",
    "execute_code": "Run",
    "delegate_task": "Delegate",
}
_PATH_KEYS = ("path", "file_path", "target_file", "filename", "file", "notebook_path")
_COMMAND_MAX = 60


def _debug(line: str) -> None:
    """Opt-in trace, for working out why a pane is not reporting."""
    if os.environ.get("HERDR_BRIDGE_DEBUG") != "1":
        return
    try:
        home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
        with open(
            os.path.join(home, "logs", "herdr-bridge.log"), "a", encoding="utf-8"
        ) as fh:
            fh.write(f"{time.time():.3f} {line}\n")
    except Exception:  # noqa: BLE001, S110 — debug must never break anything
        pass


def _target() -> tuple[str, str] | None:
    """Pane id + socket path, or None when not running inside a Herdr pane."""
    if os.environ.get("HERDR_ENV") != "1":
        return None
    pane_id = os.environ.get("HERDR_PANE_ID", "").strip()
    socket_path = os.environ.get("HERDR_SOCKET_PATH", "").strip()
    if not pane_id or not socket_path:
        return None
    return pane_id, socket_path


def _send(
    method: str, params: dict, pane_id: str | None = None, agent: str | None = None
) -> None:
    target = _target()
    if target is None:
        return
    global _seq
    own_pane, socket_path = target
    # Wall-clock ns, never going backwards. The stock plugin stamps every send
    # with a fresh time.time_ns(); a counter seeded once at import would always
    # lose to it and our state updates would be discarded as stale.
    _seq = max(time.time_ns(), _seq + 1)
    request = {
        "id": f"{SOURCE}:{int(time.time() * 1000)}:{random.randrange(1_000_000):06d}",
        "method": method,
        "params": {
            "pane_id": pane_id or own_pane,
            "source": SOURCE,
            "agent": agent or AGENT,
            "seq": _seq,
            **params,
        },
    }
    _debug(f"send {method} {json.dumps(request['params'], sort_keys=True)}")
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(_SEND_TIMEOUT)
        client.connect(socket_path)
        client.sendall((json.dumps(request) + "\n").encode("utf-8"))
        try:
            _debug(f"recv {client.recv(4096)!r}")
        except Exception:  # noqa: BLE001, S110 — ack is advisory; nothing to do with it
            pass
        client.close()
    except Exception:  # noqa: BLE001, S110 — reporting must never break the agent
        # A dead socket, a torn-down pane or a slow server are all expected and
        # must stay silent no-ops. Same posture as the stock herdr plugin.
        pass


def _tool_label(kwargs: dict) -> str | None:
    """'Edit vault_kanban_dispatch.py' from a pre_tool_call's kwargs, or None.

    The sidebar budget is one line, so the detail is the basename of the
    primary file path — the file list stays in the pane stream."""
    name = kwargs.get("tool_name")
    if not isinstance(name, str) or not name:
        return None
    args = kwargs.get("args")
    detail = ""
    if isinstance(args, dict):
        for key in _PATH_KEYS:
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                detail = value.strip().rstrip("/").rsplit("/", 1)[-1]
                break
        else:
            command = args.get("command")
            if isinstance(command, str) and command.strip():
                detail = command.strip()[:_COMMAND_MAX]
    verb = _TOOL_VERBS.get(name, name)
    return f"{verb} {detail}" if detail else verb


def _derive() -> tuple[str, str]:
    """Collapse current activity into one (state, message) for the pane."""
    if _approval:
        return "blocked", f"awaiting approval: {_approval}"
    parts: list[str] = []
    if _tool:
        parts.append(_tool)
    if _subagents:
        n = len(_subagents)
        names = ", ".join(sorted(_subagents.values())[:3])
        suffix = "" if n <= 3 else f" +{n - 3} more"
        parts.append(f"{n} subagent{'s' if n != 1 else ''}: {names}{suffix}")
    if parts:
        return "working", " · ".join(parts)
    if _busy:
        return "working", ""
    return "idle", ""


def _publish() -> None:
    """Send the derived state, but only when it actually changed."""
    global _last
    state, message = _derive()
    if (state, message) == _last:
        return
    _last = (state, message)

    params: dict[str, Any] = {"state": state}
    if message:
        params["message"] = message[:_MESSAGE_MAX]
    if _session_id:
        params["agent_session_id"] = _session_id
    _send("pane.report_agent", params)

    # `message` is accepted by report_agent but is not exposed on the agent
    # object; `display_agent` and `state_labels` are (verified against
    # `herdr agent get`), so the human-readable detail goes through metadata.
    params: dict[str, Any] = {}
    if _subagents:
        n = len(_subagents)
        params["display_agent"] = f"{AGENT} ({n} sub{'s' if n != 1 else ''})"
    else:
        params["clear_display_agent"] = True
    if message:
        params["state_labels"] = {state: message}
    else:
        params["clear_state_labels"] = True
    _send("pane.report_metadata", params)


def _subagent_key(kwargs: dict) -> str:
    for key in ("child_session_id", "subagent_id", "task_id", "tool_call_id"):
        value = kwargs.get(key)
        if isinstance(value, str) and value:
            return value
    return f"anon-{len(_subagents) + len(_child_panes)}"


# --- subagent child panes ---------------------------------------------------
#
# Same naming scheme and ordinal rules as opencode_worker (duplicated across
# trees on purpose: the Hermes plugin tree and the vault scripts share no
# import path, and both are stdlib-only by policy). A promoted subagent is an
# in-process thread, so its pane is display-only — a banner explains that,
# and the bridge reports the child's state onto it directly.


def _cli(*args: str) -> dict | None:
    """Best-effort herdr CLI call; parsed payload or None, never raises.

    Same two herdr CLI facts the dispatcher documents: success is the exit
    status (`pane run` prints nothing), and herdr reports its own errors as
    JSON on stdout with rc 0, so an error body is a failure regardless."""
    try:
        result = subprocess.run(
            [HERDR_BIN, *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:  # noqa: BLE001 — visibility must never break the agent
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return {"ok": True}
    if isinstance(payload, dict) and "error" in payload:
        return None
    return payload


def _child_prefix() -> str:
    """The scheme prefix behind this pane's name, or '' when the parent was
    never launched on the scheme — in that case subagents keep folding into
    the parent instead of getting panes."""
    m = _SCHEME_NAME_RE.match(AGENT)
    return m.group(1) if m else ""


def _next_child_name(prefix: str) -> str:
    """First free `<prefix>-hermes-NN` ordinal among live agent names."""
    payload = _cli("agent", "list") or {}
    agents = (payload.get("result") or {}).get("agents") or []
    taken = {
        str(a.get("name")) for a in agents if isinstance(a, dict) and a.get("name")
    }
    for nn in range(1, 50):
        name = f"{prefix}-hermes-{nn:02d}"
        if name not in taken:
            return name
    return f"{prefix}-hermes-99"


def _spawn_child_pane(label: str) -> tuple[str, str] | None:
    """Split a display-only pane for a subagent. (pane_id, name) or None."""
    target = _target()
    prefix = _child_prefix()
    if target is None or not prefix:
        return None
    payload = _cli("pane", "split", target[0], "--direction", "down", "--no-focus")
    pane_id = ((payload or {}).get("result") or {}).get("pane", {}).get("pane_id")
    if not pane_id:
        return None
    name = _next_child_name(prefix)
    # Report before rename: rename addresses the agent record that the report
    # creates (rename into an empty pane is a silent no-op — verified live).
    _send("pane.report_agent", {"state": "working"}, pane_id=pane_id, agent=name)
    _cli("agent", "rename", pane_id, name)
    _cli(
        "pane",
        "run",
        pane_id,
        "printf '%s\\n' "
        + "'"
        + f"↳ hermes subagent: {label[:60]}".replace("'", "'\\''")
        + "' "
        "'(an in-process thread of this tab'\\''s parent agent — "
        "this pane carries its sidebar row)'",
    )
    _send(
        "pane.report_metadata",
        {
            "display_agent": f"↳ {label[:48]}",
            "state_labels": {"working": label[:_MESSAGE_MAX]},
        },
        pane_id=pane_id,
    )
    _debug(f"subagent pane {pane_id} as {name}")
    return pane_id, name


def _finish_child_pane(pane_id: str, name: str) -> None:
    """Flip a subagent pane to `done` — retained for review with the tab."""
    _send("pane.report_agent", {"state": "idle"}, pane_id=pane_id, agent=name)
    _send(
        "pane.report_metadata",
        {
            "state_labels": {"done": "finished"},
        },
        pane_id=pane_id,
    )


def _subagent_label(kwargs: dict) -> str:
    for key in ("name", "label", "agent", "description", "task"):
        value = kwargs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:40]
    return "subagent"


# --- hooks ---------------------------------------------------------------


def on_session_start(**kwargs: Any) -> None:
    global _session_id, _busy
    with _lock:
        session_id = kwargs.get("session_id")
        if isinstance(session_id, str) and session_id:
            _session_id = session_id
        _busy = True
        _publish()


def on_session_end(**kwargs: Any) -> None:
    global _busy
    with _lock:
        _busy = False
        _subagents.clear()
        # Subagents that never got a stop hook still get their done flip.
        for pane_id, name in _child_panes.values():
            try:
                _finish_child_pane(pane_id, name)
            except Exception:  # noqa: BLE001, S110
                pass
        _child_panes.clear()
        _publish()


def pre_llm_call(**kwargs: Any) -> None:
    global _session_id, _busy
    with _lock:
        session_id = kwargs.get("session_id")
        if isinstance(session_id, str) and session_id:
            _session_id = session_id
        _busy = True
        _publish()


def pre_tool_call(**kwargs: Any) -> None:
    global _busy, _tool
    with _lock:
        _busy = True
        _tool = _tool_label(kwargs) or _tool
        _publish()


def post_tool_call(**kwargs: Any) -> None:
    global _tool
    with _lock:
        # The label reverts; the pane stays `working` while the model turns.
        _tool = None
        _publish()


def pre_approval_request(**kwargs: Any) -> None:
    """The point of this plugin: surface a permission prompt immediately."""
    global _approval
    with _lock:
        detail = kwargs.get("command") or kwargs.get("description") or "tool call"
        _approval = str(detail)[:_MESSAGE_MAX]
        _publish()


def post_approval_response(**kwargs: Any) -> None:
    global _approval, _busy
    with _lock:
        _approval = None
        # `choice` distinguishes a real decision from `timeout` -- the silent
        # headless denial. Keep it visible rather than snapping straight back
        # to a bland working state.
        if kwargs.get("choice") == "timeout":
            _busy = True
            _publish()
            _send(
                "pane.report_agent",
                {"state": "working", "message": "approval timed out -- denied"},
            )
            return
        _busy = True
        _publish()


def subagent_start(**kwargs: Any) -> None:
    with _lock:
        key = _subagent_key(kwargs)
        label = _subagent_label(kwargs)
        child = None
        try:
            child = _spawn_child_pane(label)
        except Exception as e:  # noqa: BLE001 — fall back to the fold
            _debug(f"subagent pane failed, folding: {e}")
        if child:
            _child_panes[key] = child
        else:
            _subagents[key] = label
        _publish()


def subagent_stop(**kwargs: Any) -> None:
    with _lock:
        key = _subagent_key(kwargs)
        child = _child_panes.pop(key, None)
        if child:
            try:
                _finish_child_pane(*child)
            except Exception as e:  # noqa: BLE001
                _debug(f"subagent pane finish failed: {e}")
        _subagents.pop(key, None)
        _publish()


def register(ctx) -> None:
    """Wire the lifecycle hooks. Called once by the plugin loader."""
    _debug(f"register: in_pane={_target() is not None}")
    ctx.register_hook("on_session_start", on_session_start)
    ctx.register_hook("on_session_end", on_session_end)
    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("post_tool_call", post_tool_call)
    ctx.register_hook("pre_approval_request", pre_approval_request)
    ctx.register_hook("post_approval_response", post_approval_response)
    ctx.register_hook("subagent_start", subagent_start)
    ctx.register_hook("subagent_stop", subagent_stop)
