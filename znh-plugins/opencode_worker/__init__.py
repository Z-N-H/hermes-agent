"""OpenCode Worker Plugin — registers the ``opencode_delegate`` tool.

Hermes' system prompt (see ``agent.system_prompt`` in config.yaml and
``SOUL.md``) declares a hard orchestration boundary: Hermes delegates all
coding work rather than doing it itself. This plugin provides the tool that
boundary depends on.

Registers into the ``opencode`` toolset. Add ``opencode`` to ``toolsets`` (and
to the relevant ``platform_toolsets`` entries) in config.yaml for the tool to
be exposed to the agent.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from tools.registry import tool_error, tool_result

TOOLSET = "opencode"

# When Hermes is itself running in a herdr pane, run delegated OpenCode in a
# pane of its own rather than as a captured child process, so a nested
# delegation shows up as its own agent instead of disappearing inside the
# parent's. Gated on HERDR_ENV so this is a no-op everywhere else: a plain
# `hermes chat` at a terminal keeps the original subprocess behaviour, and
# nothing new appears in a herdr the user isn't watching.
#
# The delegate pane is a split in the PARENT's tab (not a fresh throwaway
# workspace), so a delegation rolls up under its card in the sidebar. It is
# named on the dispatch scheme: when the dispatcher (or herdr_bridge) set
# HERDR_AGENT_NAME to `c<card>-<kind>-00`, the child takes the next free
# `c<card>-opencode-<nn>` ordinal; otherwise a plain `delegate-NN` fallback.
# On completion the pane is RETAINED at `done` -- the parent's tab close
# (dispatcher retention reaper) reaps it. HERDR_DELEGATE_PANES=0 remains a
# working kill switch.
#
# Deliberately duplicates ~40 lines of vault_kanban_dispatch.py's herdr lane.
# The two live in different trees (Hermes plugin vs the vault scripts, which
# are stdlib-only by policy) with no shared import path, and they place their
# log/exit files differently -- the dispatcher owns its scratch workdir, this
# must not litter a workdir the caller chose.
HERDR_BIN = os.environ.get("HERDR_BIN", "/home/znh/.local/bin/herdr")
HERDR_POLL_SECONDS = 1

_PROJECT_MARKERS = (
    ".git",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "opencode.json",
    "tsconfig.json",
    "Makefile",
)

OPENCODE_DELEGATE_SCHEMA = {
    "name": "opencode_delegate",
    "description": (
        "Delegate a coding task to the OpenCode CLI. Use this for ALL code "
        "changes — features, refactors, bug fixes, code review, writing or "
        "editing code. Never write code directly."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": (
                    "What OpenCode should do. Be specific: file paths, desired "
                    "behaviour, constraints."
                ),
            },
            "workdir": {
                "type": "string",
                "description": (
                    "Working directory, absolute or relative to the project "
                    "root. Defaults to the project root."
                ),
            },
            "model": {
                "type": "string",
                "description": (
                    "Optional model override (e.g. 'anthropic/claude-sonnet-4'). "
                    "Uses OpenCode's default if omitted."
                ),
            },
            "timeout": {
                "type": "integer",
                "description": "Max seconds to wait. Default 600.",
            },
        },
        "required": ["task"],
    },
}


def find_project_root(start: Path) -> Path:
    """Walk upward from ``start`` looking for a project marker."""
    current = start.resolve()
    for parent in [current] + list(current.parents):
        if any((parent / m).exists() for m in _PROJECT_MARKERS):
            return parent
    return current


def _resolve_workdir(workdir: str) -> Path:
    """Resolve ``workdir`` against the project root when it isn't absolute."""
    candidate = Path(workdir).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (find_project_root(Path.cwd()) / candidate).resolve()


def _resolve_opencode_bin() -> str | None:
    """Locate the opencode CLI without assuming a bare name is on PATH.

    Hermes can itself be running inside a pristine herdr pane whose PATH
    lacks ~/.bun/bin (verified 2026-08-16), in which case shutil.which alone
    reports "not found" even though opencode is installed. Fallback chain:
    PATH, then OPENCODE_BIN (same override vault_kanban_dispatch.py uses),
    then the default bun install location.

    NOTE: returns an absolute path, which _handle_opencode_delegate then
    substitutes for the bare name. In the non-herdr subprocess lane that is
    the same binary execvp would have resolved over the identical PATH, so
    the known-good behaviour of that lane is unchanged; only the 'opencode
    not found' error case changes into a successful launch when opencode
    exists off-PATH. If nothing resolves, None leaves the bare name in place
    and the existing FileNotFoundError handling reports it.
    """
    which = shutil.which("opencode")
    if which:
        return which
    override = os.environ.get("OPENCODE_BIN")
    if override:
        return override
    default = Path.home() / ".bun" / "bin" / "opencode"
    if default.is_file():
        return str(default)
    return None


def _use_herdr_pane() -> bool:
    """True when this Hermes is in a herdr pane and panes are not opted out."""
    if os.environ.get("HERDR_DELEGATE_PANES", "1") == "0":
        return False
    return (
        os.environ.get("HERDR_ENV") == "1"
        and bool(os.environ.get("HERDR_SOCKET_PATH"))
        and bool(os.environ.get("HERDR_PANE_ID"))
    )


def _herdr(*args: str, timeout: int = 30) -> tuple[bool, dict | None]:
    """Run a herdr CLI command. Returns (ok, parsed payload or None).

    Success is the exit status: `pane run` prints nothing at all, so requiring
    a parsable body would read every successful run as a failure. herdr also
    reports its own errors as JSON on stdout with a zero exit, so an error body
    is a failure regardless of the exit code.
    """
    try:
        result = subprocess.run(
            [HERDR_BIN, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False, None
    if result.returncode != 0:
        return False, None
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return True, None
    if isinstance(payload, dict) and "error" in payload:
        return False, payload
    return True, payload


_PARENT_NAME_RE = re.compile(r"^([ct][a-z0-9]+)-(?:opencode|hermes)-\d{2}$")


def _child_prefix() -> str:
    """The scheme prefix this delegation shares with its parent run.

    The dispatcher (or trigger_scanner) names the run's top pane
    `c<card>-<kind>-00` / `t<trigger>-hermes-00` and injects HERDR_AGENT_NAME
    so nested reporters stay on one prefix: a delegate of card G6W3SA6F is
    `cg6w3sa6f-opencode-NN`. Without a scheme parent (e.g. an interactive
    hermes in a hand-made pane) a neutral `delegate` prefix still keeps the
    child visible."""
    parent = os.environ.get("HERDR_AGENT_NAME", "").strip()
    m = _PARENT_NAME_RE.match(parent)
    return m.group(1) if m else "delegate"


def _next_child_name(prefix: str, kind: str) -> str:
    """First free `<prefix>-<kind>-NN` ordinal among live agent names.

    Ordinals are per card AND kind, children numbering from -01 behind the
    parent's -00. A retained `done` pane from an earlier run still holds its
    name (verified live: rename into it fails with agent_name_taken), so
    taken names are skipped rather than fought. Falls to 31 names max before
    wrapping — beyond that the sidebar row is the least of your problems."""
    taken = {
        str(a.get("name"))
        for a in (
            (_herdr("agent", "list")[1] or {}).get("result", {}).get("agents") or []
        )
        if isinstance(a, dict) and a.get("name")
    }
    for nn in range(1, 50):
        name = f"{prefix}-{kind}-{nn:02d}"
        if name not in taken:
            return name
    return f"{prefix}-{kind}-99"


def _run_in_pane(
    cmd: list[str], wd: Path, timeout: int, label: str
) -> tuple[int | None, str, str, str | None]:
    """Run `cmd` in a split of the parent's tab. Returns (rc, stdout, stderr, failure).

    `failure` is set only when no exit code was produced at all -- herdr
    unreachable, the run timing out, a pane that died early.

    stdout and stderr are kept in separate files rather than merged so the
    tool's return shape is unchanged from the subprocess path. They go to a
    temp dir, not `wd`: the caller chose that directory and it should not
    acquire stray log files as a side effect of how the run was executed.
    Exit status comes from a file because herdr's API reports agent state but
    never a process exit code.
    """
    spool = Path(tempfile.mkdtemp(prefix="herdr-delegate-"))
    # Everything below runs inside this try so the spool is removed on every
    # return path -- both `workspace create` early returns used to run before
    # any try/finally, leaking one empty mkdtemp dir per failed delegation.
    try:
        out_f, err_f, rc_f = spool / "out.log", spool / "err.log", spool / "rc"

        parent_pane = os.environ.get("HERDR_PANE_ID", "").strip()
        ok, split = _herdr(
            "pane",
            "split",
            parent_pane,
            "--direction",
            "down",
            "--no-focus",
            "--cwd",
            str(wd),
        )
        if not ok or split is None:
            return None, "", "", "herdr pane split failed"
        try:
            pane_id = split["result"]["pane"]["pane_id"]
        except (KeyError, TypeError):
            return None, "", "", "herdr pane split returned an unexpected payload"

        name = _next_child_name(_child_prefix(), "opencode")
        # The pane flips itself to done carrying the exit code -- retained
        # for review, reaped with the parent's tab by the dispatcher
        # retention sweep. Reports come after the rc write so a dead herdr
        # in the pane cannot change the verdict.
        line = (
            f"{shlex.join(cmd)} > {shlex.quote(str(out_f))} 2> {shlex.quote(str(err_f))}; "
            f"_rc=$?; echo $_rc > {shlex.quote(str(rc_f))}"
            f"; {shlex.quote(HERDR_BIN)} pane report-agent {pane_id}"
            f" --source opencode-worker --agent {shlex.quote(name)}"
            f" --state idle --seq $(date +%s%N)"
            "; if [ \"$_rc\" = 0 ]; then _lbl='done=✓ exit 0';"
            ' else _lbl="done=exit $_rc"; fi'
            f"; {shlex.quote(HERDR_BIN)} pane report-metadata {pane_id}"
            f' --source opencode-worker --state-label "$_lbl"'
            f" --seq $(date +%s%N)"
        )
        ok, _ = _herdr("pane", "run", pane_id, line)
        if not ok:
            _herdr("pane", "close", pane_id)
            return None, "", "", "herdr pane run failed"
        # Best-effort legibility; never worth failing the run over.
        # Report before rename: rename addresses the pane's agent record,
        # which a rename alone does not create (a rename into an empty pane
        # is a silent no-op — verified live).
        seq = str(time.time_ns())
        _herdr(
            "pane",
            "report-agent",
            pane_id,
            "--source",
            "opencode-worker",
            "--agent",
            name,
            "--state",
            "working",
            "--seq",
            seq,
        )
        _herdr("agent", "rename", pane_id, name)
        _herdr(
            "pane",
            "report-metadata",
            pane_id,
            "--source",
            "opencode-worker",
            "--display-agent",
            f"↳ {label[:40]}",
            "--seq",
            seq,
        )

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if rc_f.exists():
                raw = rc_f.read_text(errors="replace").strip()
                out = out_f.read_text(errors="replace") if out_f.exists() else ""
                err = err_f.read_text(errors="replace") if err_f.exists() else ""
                try:
                    return int(raw), out, err, None
                except ValueError:
                    return None, out, err, f"unreadable exit code: {raw[:40]!r}"
            time.sleep(HERDR_POLL_SECONDS)
        # Closing the pane is what stops a timed-out run; unlike the old
        # whole-workspace close it leaves the parent (and the shared client
        # workspace) untouched.
        _herdr("pane", "close", pane_id)
        return None, "", "", f"OpenCode timed out after {timeout}s"
    finally:
        # rmtree, not unlink/rmdir: a failing unlink or a not-quite-empty
        # spool inside a finally would mask the run's real return value.
        shutil.rmtree(spool, ignore_errors=True)


def _handle_opencode_delegate(args: dict, **_: Any) -> str:
    task = str(args.get("task") or "").strip()
    if not task:
        return tool_error("task is required")

    try:
        timeout = int(args.get("timeout") or 600)
    except (TypeError, ValueError):
        return tool_error("timeout must be an integer number of seconds")

    wd = _resolve_workdir(str(args.get("workdir") or "."))
    if not wd.is_dir():
        return tool_error(f"workdir does not exist: {wd}")

    cmd = ["opencode", "run"]
    model = str(args.get("model") or "").strip()
    if model:
        cmd.extend(["--model", model])
    cmd.append(task)

    # Delegate panes run `cmd` in a fresh server-side shell whose PATH need
    # not match Hermes' (verified 2026-08-16: this server augments PATH from
    # ~/.opencode/bin and ~/.local/bin only, so a bare `opencode` -- which
    # lives in ~/.bun/bin -- is not resolvable in a delegate pane and every
    # delegation would exit 127). Resolve once here, in Hermes' own
    # environment. The subprocess lane's execvp would find the same first
    # match over the identical PATH, so its behaviour is unchanged when
    # opencode is on PATH at all; when nothing resolves we leave the bare name
    # so the subprocess lane keeps its FileNotFoundError handling ("not found
    # in PATH").
    resolved = _resolve_opencode_bin()
    if resolved:
        cmd[0] = resolved

    if _use_herdr_pane():
        label = f"delegate:{task[:40]}"
        rc, stdout, stderr, failure = _run_in_pane(cmd, wd, timeout, label)
        if failure:
            return tool_error(
                failure, workdir=str(wd), stdout=stdout.strip(), stderr=stderr.strip()
            )
    else:
        env = os.environ.copy()
        env.setdefault(
            "OPENCODE_CONFIG_HOME", str(Path.home() / ".config" / "opencode")
        )
        try:
            result = subprocess.run(
                cmd, cwd=wd, env=env, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return tool_error(f"OpenCode timed out after {timeout}s", workdir=str(wd))
        except FileNotFoundError:
            return tool_error("'opencode' not found in PATH")
        except Exception as e:  # noqa: BLE001 — surface anything to the agent
            return tool_error(f"{type(e).__name__}: {e}", workdir=str(wd))
        rc, stdout, stderr = result.returncode, result.stdout, result.stderr

    if rc != 0:
        return tool_error(
            f"OpenCode exited {rc}",
            workdir=str(wd),
            stdout=stdout.strip(),
            stderr=stderr.strip(),
        )

    return tool_result({
        "workdir": str(wd),
        "output": stdout.strip(),
        "stderr": stderr.strip(),
    })


def _check_opencode_available() -> bool:
    """Gate exposure of the tool on the OpenCode CLI actually being installed.

    Must use the same resolution chain as the handler: inside a herdr pane
    shutil.which alone fails (server-side PATH lacks ~/.bun/bin), which hid
    the tool entirely even though opencode was installed (found 2026-08-16:
    headless Hermes in a pane reported opencode_delegate missing).
    """
    return _resolve_opencode_bin() is not None


def register(ctx) -> None:
    """Register the opencode_delegate tool. Called once by the plugin loader."""
    ctx.register_tool(
        name="opencode_delegate",
        toolset=TOOLSET,
        schema=OPENCODE_DELEGATE_SCHEMA,
        handler=_handle_opencode_delegate,
        check_fn=_check_opencode_available,
        description=OPENCODE_DELEGATE_SCHEMA["description"],
        emoji="🛠",
    )
