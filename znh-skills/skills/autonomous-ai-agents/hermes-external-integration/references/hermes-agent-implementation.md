# HermesAgent Adapter — Real Implementation Reference

Condensed reference derived from the actual HermesAgent adapter built for Agno AgentOS (Purple Phoenix Task 267).

## Files

| File | Purpose |
|------|---------|
| `agent_context/hermes_agent.py` | The adapter class (`HermesAgent`) |
| `tests/test_hermes_agent.py` | 22 tests covering protocol compliance, session mapping, streaming, error handling |
| `examples/agentos_hermes.py` | Standalone demo: registers HermesAgent with AgentOS and runs a chat |
| `agent_context/scripts/serve_agno.py` | uvicorn ASGI runner that instantiates AgentOS + HermesAgent and serves the FastAPI app |

## Adapter Skeleton

```python
"""HermesAgent — Agno BaseExternalAgent adapter for the Hermes CLI."""

import asyncio
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Optional
from uuid import uuid4

from agno.agents.base import BaseExternalAgent
from agno.run.events import RunContentEvent


@dataclass
class HermesAgent(BaseExternalAgent):
    """Adapter that wraps ``hermes chat`` as an Agno external agent."""

    max_turns: int = 10
    hermes_bin: str = "hermes"
    model: str = "default"
    provider: str = "default"
    toolsets: str = ""
    working_dir: Optional[str] = None
    framework: str = "hermes"

    # Maps Agno session_id → Hermes session_id for resumption.
    _hermes_session_ids: Dict[str, str] = field(
        default_factory=dict, init=False, repr=False
    )

    # ------------------------------------------------------------------
    # Adapter hooks (required by BaseExternalAgent)
    # ------------------------------------------------------------------

    async def _arun_adapter(self, input, *, history=None, **kwargs) -> str:
        agno_sid = kwargs.get("session_id")
        hermes_sid = self._hermes_session_ids.get(agno_sid)

        result = await asyncio.to_thread(
            self._run_hermes, str(input), hermes_session_id=hermes_sid
        )
        if result.returncode != 0:
            raise RuntimeError(self._format_error(result))

        self._maybe_store_session(result.stderr, agno_sid)
        return result.stdout

    async def _arun_adapter_stream(
        self, input, *, history=None, **kwargs
    ) -> AsyncIterator[Any]:
        run_id = kwargs.get("run_id", str(uuid4()))
        agno_sid = kwargs.get("session_id")
        hermes_sid = self._hermes_session_ids.get(agno_sid)

        result = await asyncio.to_thread(
            self._run_hermes, str(input), hermes_session_id=hermes_sid
        )
        if result.returncode != 0:
            raise RuntimeError(self._format_error(result))

        self._maybe_store_session(result.stderr, agno_sid)

        content = result.stdout
        if content:
            yield RunContentEvent(
                run_id=run_id,
                agent_id=self.get_id(),
                agent_name=self.name or "",
                content=content,
            )

    # ------------------------------------------------------------------
    # Hermes subprocess
    # ------------------------------------------------------------------

    def _run_hermes(self, prompt: str, *, hermes_session_id: Optional[str] = None):
        cmd = [
            self.hermes_bin,
            "chat",
            "-q",  # quiet mode — suppresses the TUI and spinner
            "-m",
            self.model,
            "--provider",
            self.provider,
        ]
        if hermes_session_id:
            cmd += ["--resume", hermes_session_id]
        if self.toolsets:
            cmd += ["-t", self.toolsets]
        if self.working_dir:
            cmd += ["--worktree"]

        env = os.environ.copy()
        env["HERMES_QUIET"] = "1"
        if self.working_dir:
            env["HERMES_CWD"] = self.working_dir

        return subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            env=env,
        )

    # ------------------------------------------------------------------
    # Session-id mapping
    # ------------------------------------------------------------------

    def _maybe_store_session(self, stderr: str, agno_sid: Optional[str]) -> None:
        if not agno_sid:
            return
        sid = self._parse_session_id(stderr)
        if sid and sid != self._hermes_session_ids.get(agno_sid):
            self._hermes_session_ids[agno_sid] = sid

    @staticmethod
    def _parse_session_id(stderr: str) -> Optional[str]:
        match = re.search(r"session_id:\s*(\S+)", stderr or "")
        return match.group(1) if match else None

    def _format_error(self, result: subprocess.CompletedProcess) -> str:
        parts = [f"Hermes exited with code {result.returncode}"]
        if result.stderr:
            parts.append(f"stderr: {result.stderr[:500]}")
        return "\n".join(parts)
```

## Key Implementation Details

### Quiet mode (`-q`)

Hermes's default TUI mode captures the terminal and writes spinner/status to stdout. This breaks adapters because:
1. TUI control sequences pollute the captured output
2. The spinner runs asynchronously and may not finish before `subprocess.run` returns

Always use `hermes chat -q` (or set `HERMES_QUIET=1`) for adapter use. Quiet mode suppresses the TUI and outputs clean text.

### Session ID mapping

The adapter stores a mapping from Agno's `session_id` to Hermes's internal session ID. On first run:
1. Hermes creates a new session and prints `session_id: <uuid>` to stderr
2. The adapter parses this and stores it in `_hermes_session_ids`
3. On subsequent runs with the same Agno session, the adapter passes `--resume <hermes_session_id>`

This is critical for multi-turn conversations. Without it, every Agno run creates a brand-new Hermes session and loses all context.

### Tool call visibility

Hermes quiet mode does **not** expose individual tool call events. The adapter yields a single `RunContentEvent` with the final response. Tool calls appear as plain text inside the response (e.g., "I used the web_search tool to find...").

If you need structured tool call events in the Agno trace UI, you must either:
- Patch Hermes to emit structured tool events (non-trivial)
- Parse the response text heuristically (fragile)
- Accept that tool calls show up as content, not discrete events

### Async/subprocess bridge

Always wrap `subprocess.run` in `asyncio.to_thread()` to avoid blocking the Agno event loop:

```python
result = await asyncio.to_thread(
    self._run_hermes, str(input), hermes_session_id=hermes_sid
)
```

Direct `subprocess.run` in an async hook blocks all other concurrent requests.

## Testing

Mock `subprocess.run` in tests — never invoke the real Hermes CLI:

```python
from unittest.mock import patch

FAKE_STDERR = "session_id: test-uuid-1234\n"
FAKE_STDOUT = "Hello from Hermes"


def _fake_run(*args, **kwargs):
    return subprocess.CompletedProcess(
        args=args[0] if args else ["hermes"],
        returncode=0,
        stdout=FAKE_STDOUT,
        stderr=FAKE_STDERR,
    )


@pytest.mark.asyncio
async def test_adapter_returns_content():
    agent = HermesAgent(name="Test")
    with patch("agent_context.hermes_agent.subprocess.run", side_effect=_fake_run):
        result = await agent.arun("hi")
    assert result == FAKE_STDOUT
```

Required test coverage:
1. `isinstance(agent, BaseExternalAgent)`
2. `agent.framework == "hermes"`
3. ID autogeneration (`get_id()` non-empty after `__post_init__`)
4. `_arun_adapter` and `_arun_adapter_stream` are callable
5. Correct command building (quiet flag, resume flag conditional)
6. Session ID parsing from stderr
7. Session mapping storage and retrieval
8. Cross-session isolation (different Agno sessions → different Hermes sessions)
9. Streaming event sequence (`RunStarted → RunContent → RunCompleted`)
10. Error handling (`RunErrorEvent` on non-zero exit)

## AgentOS Registration

```python
from agno.os import AgentOS
from agno.db.sqlite import SqliteDb
from agent_context.hermes_agent import HermesAgent

agent = HermesAgent(
    name="Hermes",
    model="hf:moonshotai/Kimi-K2.6",
    provider="custom",
    toolsets="web,terminal,file",
)
agent_os = AgentOS(agents=[agent], db=SqliteDb(db_file="agno.db"))
app = agent_os.get_app()  # FastAPI app
```

Serve with uvicorn:
```python
import uvicorn

uvicorn.run(app, host="127.0.0.1", port=9120)
```

Or use the provided `agent_context/scripts/serve_agno.py` which handles `sys.path` setup for editable installs and registers the agent automatically.

## Serve Script (`serve_agno.py`)

The provided script:
1. Adds the project root to `sys.path` so `agent_context` imports work in editable installs
2. Imports `HermesAgent` from `agent_context.hermes_agent`
3. Creates `AgentOS`, registers the agent, and calls `get_app()`
4. Serves via uvicorn on `AGNO_HOST` / `AGNO_PORT` (defaults: 127.0.0.1:9120)

```bash
# Foreground
python agent_context/scripts/serve_agno.py

# Background
nohup python agent_context/scripts/serve_agno.py > /tmp/agno.log 2>&1 &
```

## Pitfalls

1. **Forgetting `-q` on `hermes chat`:** TUI mode breaks output capture. Always use quiet mode.
2. **Missing `sys.path` in serve script:** When Pantheon is installed as a uv tool, `agent_context` is not on `sys.path` by default. The serve script adds it explicitly.
3. **Blocking subprocess in async hook:** Wrap `subprocess.run` in `asyncio.to_thread`.
4. **Session ID not parsed:** If Hermes changes its stderr format, `_parse_session_id` breaks and resumption stops working. Monitor stderr format across Hermes releases.
5. **Tool call events not available:** Don't invent synthetic tool events. A single `RunContentEvent` is correct for quiet mode.
6. **Yielding terminal events from adapter:** `RunStartedEvent` / `RunCompletedEvent` / `RunErrorEvent` are owned by `BaseExternalAgent`. Raise on error; let the base class emit terminals.
7. **Environment propagation:** Hermes reads `HERMES_HOME`, `HERMES_CWD`, and profile config from the environment. Ensure these are set correctly when spawning from the adapter.
