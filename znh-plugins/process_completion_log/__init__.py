"""Process Completion Log — durable record of every background process's outcome.

When a background `terminal(... notify_on_complete=true)` process finishes,
Hermes gets a conversational notification with a truncated output tail -- but
nothing forces it to retrieve the full result or write it anywhere
persistent. Confirmed in practice: a session fired off OpenCode delegations,
got the completion pings, and never wrote the results to a note, a card, or
anywhere else -- the output was gone the moment the conversation moved on.

This plugin closes that specific gap (not the "was the result acted on"
question, which still needs a human or a later session to reconcile, but the
narrower "is the result recoverable at all" question): it appends one JSON
line per completed process to `~/.hermes/process-completions.jsonl` via the
`on_process_complete` hook, which fires from
`tools/process_registry.py::ProcessRegistry._move_to_finished()` regardless
of whether `notify_on_complete` was set or whether the model ever reads the
ping. Plain append-only JSONL -- no schema/migration, safe under concurrent
writes at this volume.
"""

from __future__ import annotations

import json
import time
from typing import Any

from hermes_constants import get_hermes_home

LOG_PATH_NAME = "process-completions.jsonl"


def on_process_complete(
    session_id: str = "",
    session_key: str = "",
    command: str = "",
    cwd: "str | None" = None,
    exit_code: "int | None" = None,
    task_id: str = "",
    output: str = "",
    **kwargs: Any,
) -> None:
    record = {
        "completed_at": time.time(),
        "session_id": session_id,
        "session_key": session_key,
        "command": command,
        "cwd": cwd,
        "exit_code": exit_code,
        "task_id": task_id,
        "output": output,
    }
    log_path = get_hermes_home() / LOG_PATH_NAME
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def register(ctx) -> None:
    """Register the on_process_complete logger. Called once by the plugin loader."""
    ctx.register_hook("on_process_complete", on_process_complete)
