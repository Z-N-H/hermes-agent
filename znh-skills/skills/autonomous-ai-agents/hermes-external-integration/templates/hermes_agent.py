"""Template: HermesAgent adapter for Agno AgentOS.

Copy and modify for your own CLI-based agent. This is the exact adapter that
was validated against Agno 2.6.18. Key modification points are marked with
`# CUSTOMIZE:` comments.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from agno.agents.base import BaseExternalAgent
from agno.run.agent import RunContentEvent, RunOutputEvent


@dataclass
class HermesAgent(BaseExternalAgent):
    """Adapter for the Hermes CLI, exposing it as an Agno external agent.

    Hermes manages its own memory and tool execution internally
    (~/.hermes/state.db); Agno only receives the final response text and
    session/resume metadata.
    """

    # CUSTOMIZE: display name for this agent (required).
    name: str = "Hermes Agent"

    # CUSTOMIZE: maximum guest turns per run.
    max_turns: int = 10

    # CUSTOMIZE: working directory for the subprocess (None = inherit).
    cwd: Optional[str] = None

    # CUSTOMIZE: binary name or absolute path.
    hermes_bin: str = "hermes"

    # FIXED: framework label used in traces and UI panels.
    framework: str = "hermes"

    # Maps Agno session_id -> Hermes session_id.
    _hermes_session_ids: Dict[str, str] = field(
        default_factory=dict, init=False, repr=False
    )

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
            "-Q",  # quiet mode — only final response + session metadata
            "--max-turns",
            str(self.max_turns),
        ]
        if hermes_session_id:
            cmd.extend(["--resume", hermes_session_id])
        return cmd

    def _run_hermes(
        self, prompt: str, *, hermes_session_id: Optional[str] = None
    ) -> subprocess.CompletedProcess:
        """Run the Hermes CLI synchronously."""
        cmd = self._build_command(prompt, hermes_session_id=hermes_session_id)
        return subprocess.run(cmd, capture_output=True, text=True, cwd=self.cwd)

    # ------------------------------------------------------------------
    # stderr metadata parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_session_id(stderr: str) -> Optional[str]:
        """Extract the guest session id from a ``session_id: <id>`` stderr line."""
        match = re.search(r"session_id:\s*(\S+)", stderr or "")
        return match.group(1) if match else None

    def _maybe_store_session(self, stderr: str, agno_session_id: Optional[str]) -> None:
        """Record the guest session id for a host session so it can be resumed."""
        if not agno_session_id:
            return
        hermes_session_id = self._parse_session_id(stderr)
        if hermes_session_id:
            self._hermes_session_ids[agno_session_id] = hermes_session_id

    @staticmethod
    def _format_error(result: subprocess.CompletedProcess) -> str:
        """Build a human-readable error message for a non-zero exit."""
        detail = (result.stderr or "").strip() or (result.stdout or "").strip()
        return f"Hermes CLI exited with code {result.returncode}: {detail}"

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
        """Non-streaming: run once and return the final response text."""
        agno_session_id = kwargs.get("session_id")
        hermes_session_id = (
            self._hermes_session_ids.get(agno_session_id) if agno_session_id else None
        )

        result = await asyncio.to_thread(
            self._run_hermes, str(input), hermes_session_id=hermes_session_id
        )

        if result.returncode != 0:
            raise RuntimeError(self._format_error(result))

        self._maybe_store_session(result.stderr, agno_session_id)
        return result.stdout

    async def _arun_adapter_stream(
        self,
        input: Any,
        *,
        history: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> AsyncIterator[RunOutputEvent]:
        """Streaming: run once and yield the final response as content.

        Terminal events (RunStarted/RunCompleted/RunError) are handled by the
        base class — this hook only yields content events.
        """
        run_id = kwargs.get("run_id", str(uuid4()))
        agno_session_id = kwargs.get("session_id")
        hermes_session_id = (
            self._hermes_session_ids.get(agno_session_id) if agno_session_id else None
        )

        result = await asyncio.to_thread(
            self._run_hermes, str(input), hermes_session_id=hermes_session_id
        )

        if result.returncode != 0:
            raise RuntimeError(self._format_error(result))

        self._maybe_store_session(result.stderr, agno_session_id)

        content = result.stdout
        if content:
            yield RunContentEvent(
                run_id=run_id,
                agent_id=self.get_id(),
                agent_name=self.name or "",
                content=content,
            )
