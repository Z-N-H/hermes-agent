"""
Production-ready Hermes adapter for Agno AgentOS.

Features:
- Persistent worker process eliminates Python interpreter cold-start (~1-2s).
- Real-time streaming: stdout chunks are yielded as RunContentEvent as they arrive.
- Session ID mapping for resumption across Agno ↔ Hermes sessions.
- Graceful error handling with stderr capture.

Usage::

    from agent_context.hermes_agent import HermesAgent
    from agno.os import AgentOS
    from agno.db.sqlite.sqlite import SqliteDb

    agent = HermesAgent(name="Hermes Coder", max_turns=3)
    db = SqliteDb(db_file="/tmp/agno_os.db")
    agent_os = AgentOS(agents=[agent], db=db)
    app = agent_os.get_app()
"""

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from agno.agents.base import BaseExternalAgent
from agno.run.agent import RunContentEvent, RunOutputEvent


@dataclass
class HermesAgent(BaseExternalAgent):
    """Adapter for the Hermes CLI, exposing it as an Agno external agent.

    Uses a **persistent worker process** to eliminate Python interpreter
    cold-start (~1–2 s) and **streams stdout in real-time** so the UI shows
    a "typing" effect instead of a frozen spinner.

    Hermes manages its own memory and tool execution internally
    (``~/.hermes/state.db``); Agno only receives the final response text and
    session/resume metadata.

    Args:
        name: Display name for this agent.
        id: Unique identifier (auto-generated from name if not set).
        description: Optional description.
        max_turns: Maximum number of Hermes agentic turns (default 3 for speed).
        cwd: Working directory for the Hermes subprocess.
        hermes_bin: Name or path of the Hermes CLI binary.
    """

    max_turns: int = 3
    cwd: Optional[str] = None
    hermes_bin: str = "hermes"
    framework: str = "hermes"

    # Maps Agno session_id -> Hermes session_id.
    _hermes_session_ids: Dict[str, str] = field(
        default_factory=dict, init=False, repr=False
    )

    # Persistent worker: {session_id: asyncio.subprocess.Process}
    _workers: Dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    # ------------------------------------------------------------------
    # Command building
    # ------------------------------------------------------------------

    def _build_command(
        self, prompt: str, *, hermes_session_id: Optional[str] = None
    ) -> List[str]:
        """Build the ``hermes chat`` argv for a one-shot quiet run."""
        cmd: List[str] = [
            self.hermes_bin,
            "chat",
            "-q",
            prompt,
            "-Q",
            "--max-turns",
            str(self.max_turns),
        ]
        if hermes_session_id:
            cmd.extend(["--resume", hermes_session_id])
        return cmd

    # ------------------------------------------------------------------
    # Worker management
    # ------------------------------------------------------------------

    def _worker_path(self) -> str:
        """Path to the persistent worker script (see hermes_worker.py)."""
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "scripts",
            "hermes_worker.py",
        )

    async def _get_worker(self, session_id: str) -> asyncio.subprocess.Process:
        """Return (or start) the persistent worker for a session."""
        if session_id in self._workers:
            proc = self._workers[session_id]
            if proc.returncode is None:
                return proc
            # Worker died — restart it
            del self._workers[session_id]

        worker_path = self._worker_path()
        if not os.path.isfile(worker_path):
            # Fallback: use the current interpreter (worker not available)
            worker_path = sys.executable

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            worker_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._workers[session_id] = proc
        return proc

    # ------------------------------------------------------------------
    # stderr metadata parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_session_id(stderr: str) -> Optional[str]:
        """Extract the Hermes session id from a ``session_id: <id>`` stderr line."""
        match = re.search(r"session_id:\s*(\S+)", stderr or "")
        return match.group(1) if match else None

    def _maybe_store_session(self, stderr: str, agno_session_id: Optional[str]) -> None:
        """Record the Hermes session id for an Agno session so it can be resumed."""
        if not agno_session_id:
            return
        hermes_session_id = self._parse_session_id(stderr)
        if hermes_session_id:
            self._hermes_session_ids[agno_session_id] = hermes_session_id

    @staticmethod
    def _format_error(returncode: int, stderr: str) -> str:
        """Build a human-readable error message for a non-zero Hermes exit."""
        detail = (stderr or "").strip()
        return f"Hermes CLI exited with code {returncode}: {detail}"

    # ------------------------------------------------------------------
    # BaseExternalAgent hooks
    # ------------------------------------------------------------------

    async def _arun_adapter(
        self,
        input: Any,
        *,
        history: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> str:
        """Non-streaming: collect all streamed content and return the final text."""
        parts = []
        async for event in self._arun_adapter_stream(input, history=history, **kwargs):
            if isinstance(event, RunContentEvent):
                parts.append(event.content)
        return "".join(parts)

    async def _arun_adapter_stream(
        self,
        input: Any,
        *,
        history: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[RunOutputEvent]:
        """Streaming: send the prompt to the persistent worker and yield
        ``RunContentEvent`` chunks as stdout arrives in real-time.
        """
        run_id = kwargs.get("run_id", str(uuid4()))
        agno_session_id = kwargs.get("session_id")
        hermes_session_id = (
            self._hermes_session_ids.get(agno_session_id) if agno_session_id else None
        )

        proc = await self._get_worker(agno_session_id or "default")

        # Send request to worker via stdin (JSON line)
        req = json.dumps({
            "prompt": str(input),
            "max_turns": self.max_turns,
            "session_id": hermes_session_id,
        })
        proc.stdin.write(req.encode("utf-8") + b"\n")
        await proc.stdin.drain()

        # Read streaming response from worker stdout line-by-line
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "chunk":
                yield RunContentEvent(
                    run_id=run_id,
                    agent_id=self.get_id(),
                    agent_name=self.name or "",
                    content=msg["data"],
                )
            elif msg.get("type") == "done":
                if msg.get("returncode", 0) != 0:
                    raise RuntimeError(
                        self._format_error(msg["returncode"], msg.get("stderr", ""))
                    )
                self._maybe_store_session(msg.get("stderr", ""), agno_session_id)
                break


# ── Standalone sanity check ──────────────────────────────────────────────────
if __name__ == "__main__":
    agent = HermesAgent(name="Hermes Dev Agent")
    result = asyncio.run(agent.arun("What is 2+2?"))
    print(result)
