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


def opencode_delegate(
    task: str, workdir: str = ".", model: Optional[str] = None, timeout: int = 600
) -> str:
    """
    Delegate a coding task to OpenCode CLI.

    Args:
        task: Description of what OpenCode should do
        workdir: Working directory (absolute or relative to project root)
        model: Optional model override (e.g., "anthropic/claude-sonnet-4")
        timeout: Max seconds to wait (default 600)

    Returns:
        OpenCode's output as string
    """
    # Resolve workdir
    wd = Path(workdir).resolve()
    if not wd.is_absolute():
        wd = find_project_root(Path.cwd()) / wd

    guard_error = _reject_unregistered_project_dir(wd)
    if guard_error:
        return guard_error

    # Build command
    cmd = ["opencode", "run"]
    if model:
        cmd.extend(["--model", model])
    cmd.append(task)

    # Run
    env = os.environ.copy()
    # Ensure OpenCode can find its config
    env.setdefault("OPENCODE_CONFIG_HOME", str(Path.home() / ".config" / "opencode"))

    try:
        result = subprocess.run(
            cmd, cwd=wd, env=env, capture_output=True, text=True, timeout=timeout
        )
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

    if len(sys.argv) < 2:
        print("Usage: python opencode_delegate.py '<task>' [workdir] [model]")
        sys.exit(1)

    task = sys.argv[1]
    workdir = sys.argv[2] if len(sys.argv) > 2 else "."
    model = sys.argv[3] if len(sys.argv) > 3 else None

    print(opencode_delegate(task, workdir, model))
