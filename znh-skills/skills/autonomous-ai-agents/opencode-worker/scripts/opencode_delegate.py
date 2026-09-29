#!/usr/bin/env python3
"""OpenCode delegation tool - runs opencode run for coding tasks."""

import os
import json
import subprocess
import shlex
from pathlib import Path
from typing import Optional

PANTHEON_ROOT = Path(os.environ.get("PANTHEON_ROOT", "/mnt/z/pantheon"))


def find_project_root(start: Path) -> Path:
    """Find project root by looking for common markers."""
    markers = [
        ".git",
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "go.mod",
        "opencode.json",
        "tsconfig.json",
        "Makefile",
    ]
    current = start.resolve()
    for parent in [current] + list(current.parents):
        if any((parent / m).exists() for m in markers):
            return parent
    return current


def _reject_unregistered_project_dir(wd: Path) -> Optional[str]:
    """Refuse to run inside a fabricated `projects/<name>` directory.

    `projects/` is reserved for real Pantheon projects: a codename with its
    own git repo, registered in `registry.json`. A one-off/manual delegation
    (this tool, called ad hoc rather than through vault_kanban_dispatch.py)
    has no other guard stopping it from being pointed at
    `projects/<made-up-name>` and quietly creating what looks like a real
    project but isn't. That happened for real on 2026-08-03 during a pipeline
    outage: a manually-typed brief pointed OpenCode at
    `projects/thankbox-bulk-christmas-cards`, which had no `.git` and no
    registry entry — a scratch task masquerading as a project. Ad hoc/scratch
    work belongs in `scratch/NNN-slug/` instead.
    """
    try:
        rel = wd.relative_to(PANTHEON_ROOT / "projects")
    except ValueError:
        return None
    if not rel.parts:
        return None
    project_name = rel.parts[0]
    project_dir = PANTHEON_ROOT / "projects" / project_name
    registry_path = PANTHEON_ROOT / "registry.json"
    registered = False
    if registry_path.is_file():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            registered = project_name in registry.get("projects", {})
        except (json.JSONDecodeError, OSError):
            registered = False
    if registered and (project_dir / ".git").exists():
        return None
    return (
        f"ERROR: refusing to run in 'projects/{project_name}' — it is not a "
        f"registered Pantheon project (no registry.json entry and/or no "
        f".git). Do not invent a new directory under projects/. Use a "
        f"scratch/NNN-slug workdir for ad hoc or research work instead."
    )


def extract_session_id(stream: str) -> Optional[str]:
    """First sessionID in an `opencode run --format json` event stream.

    Events are one JSON object per line and each carries a top-level
    `sessionID`. Anything unparseable is skipped, so the answer is simply
    None — the caller then proceeds exactly as a plain one-shot would.
    """
    for line in stream.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            sid = event.get("sessionID")
            if isinstance(sid, str) and sid:
                return sid
    return None


def extract_text_output(stream: str) -> str:
    """Assistant text reassembled from a `--format json` event stream.

    Each text event carries the full chunk in `part.text`, so joining those
    in stream order reconstructs the reply. Empty if the stream has no text
    events — the caller falls back to the raw stream.
    """
    parts = []
    for line in stream.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        part = event.get("part")
        if (isinstance(part, dict) and part.get("type") == "text"
                and isinstance(part.get("text"), str) and part["text"].strip()):
            parts.append(part["text"].strip())
    return "\n\n".join(parts)


def _render_continuation_output(result, session_file: Optional[str]) -> str:
    """Render a `--format json` run like a plain run, plus the session id.

    The resolved session id is written back to `session_file` (best-effort —
    bookkeeping must never fail a delegation) and appended to the output as a
    `--- session_id: <id> ---` line so the caller can continue it later with
    `session=<id>`. If the stream yields no id the run is still reported
    normally, just without the marker.
    """
    stream = result.stdout or ""
    output = extract_text_output(stream) or stream
    if result.stderr:
        output += f"\n--- stderr ---\n{result.stderr}"
    if result.returncode != 0:
        output += f"\n--- exit code: {result.returncode} ---"
    resolved = extract_session_id(stream)
    if resolved:
        if session_file:
            try:
                Path(session_file).write_text(resolved + "\n", encoding="utf-8")
            except OSError:
                pass
        output += f"\n--- session_id: {resolved} ---"
    return output.strip()


def opencode_delegate(
    task: str, workdir: str = ".", model: Optional[str] = None, timeout: int = 600,
    session: Optional[str] = None, session_file: Optional[str] = None
) -> str:
    """
    Delegate a coding task to OpenCode CLI.

    Args:
        task: Description of what OpenCode should do
        workdir: Working directory (absolute or relative to project root)
        model: Optional model override (e.g., "anthropic/claude-sonnet-4")
        timeout: Max seconds to wait (default 600)
        session: Optional OpenCode session id to continue (`-s <id>`) — pass
            the id from a previous delegation's `session_id` marker to resume
            that session instead of starting a fresh one
        session_file: Optional path whose stored session id is read (when
            `session` is not given) and updated after the run — a durable
            handle for multi-part work spread across separate delegations

    Returns:
        OpenCode's output as string. With `session`/`session_file` the id of
        the session that ran is appended as `--- session_id: <id> ---`.
    """
    # Resolve workdir
    wd = Path(workdir).resolve()
    if not wd.is_absolute():
        wd = find_project_root(Path.cwd()) / wd

    guard_error = _reject_unregistered_project_dir(wd)
    if guard_error:
        return guard_error

    # Session continuity: with `session`/`session_file` the run must emit
    # `--format json` so its session id can be extracted afterwards; without
    # them the invocation (and output shape) is exactly what it has always
    # been.
    if session_file and not session:
        try:
            stored = Path(session_file).read_text(encoding="utf-8").strip()
            session = stored or None
        except OSError:
            pass

    # Build command
    cmd = ["opencode", "run"]
    if model:
        cmd.extend(["--model", model])
    if session or session_file:
        cmd.extend(["--format", "json"])
    if session:
        cmd.extend(["-s", session])
    cmd.append(task)

    # Run
    env = os.environ.copy()
    # Ensure OpenCode can find its config
    env.setdefault("OPENCODE_CONFIG_HOME", str(Path.home() / ".config" / "opencode"))

    try:
        result = subprocess.run(
            cmd, cwd=wd, env=env, capture_output=True, text=True, timeout=timeout
        )
        if session or session_file:
            return _render_continuation_output(result, session_file)
        output = result.stdout
        if result.stderr:
            output += f"\n--- stderr ---\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n--- exit code: {result.returncode} ---"
        return output.strip()
    except subprocess.TimeoutExpired:
        return f"ERROR: OpenCode timed out after {timeout}s"
    except FileNotFoundError:
        return (
            "ERROR: 'opencode' not found in PATH. Install with: npm i -g @opencode/cli"
        )
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


if __name__ == "__main__":
    import sys

    positional = []
    session = None
    session_file = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--session" and i + 1 < len(args):
            session = args[i + 1]
            i += 2
        elif args[i] == "--session-file" and i + 1 < len(args):
            session_file = args[i + 1]
            i += 2
        else:
            positional.append(args[i])
            i += 1

    if not positional:
        print("Usage: python opencode_delegate.py '<task>' [workdir] [model] "
              "[--session <id>] [--session-file <path>]")
        sys.exit(1)

    task = positional[0]
    workdir = positional[1] if len(positional) > 1 else "."
    model = positional[2] if len(positional) > 2 else None

    print(opencode_delegate(task, workdir, model,
                            session=session, session_file=session_file))
