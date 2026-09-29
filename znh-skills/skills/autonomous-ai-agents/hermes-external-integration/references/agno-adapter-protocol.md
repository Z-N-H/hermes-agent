# Agno Adapter Protocol — Condensed API Surface

> Extracted from Agno 2.6.18 (`agno/agents/base.py`, `agno/agents/claude/agent.py`, `agno/agent/protocol.py`, `agno/run/agent.py`).

## BaseExternalAgent

```python
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional


@dataclass
class BaseExternalAgent:
    name: Optional[str] = None
    id: Optional[str] = None  # auto-generated from name in __post_init__
    description: Optional[str] = None
    framework: str = "external"
    markdown: bool = True
    db: Optional[Any] = None  # session persistence backend

    # Internal: session store mapping
    # _sdk_session_ids: Dict[str, str] = field(default_factory=dict, init=False, repr=False)
```

### Required Subclass Hooks

```python
async def _arun_adapter(
    self, input: Any, *, history: Optional[List[Dict[str, Any]]] = None, **kwargs: Any
) -> Any:
    """Non-streaming. Return the response content.
    kwargs includes `session` (loaded AgentSession) and `session_id`.
    Mutate `session.session_data` in place for guest-specific state.
    """
    raise NotImplementedError


async def _arun_adapter_stream(
    self, input: Any, *, history: Optional[List[Dict[str, Any]]] = None, **kwargs: Any
) -> AsyncIterator[RunOutputEvent]:
    """Streaming. Yield RunContentEvent, ToolCallStartedEvent, etc.
    Do NOT yield RunStartedEvent or RunCompletedEvent — base class handles those.
    """
    raise NotImplementedError
    yield  # type: ignore
```

### Public API Entrypoints

```python
def arun(self, input, *, stream=None, session_id=None, user_id=None, ...)
    # If stream=True → returns AsyncIterator[RunOutputEvent]
    # If stream=False → returns coroutine → RunOutput

def run(self, input, *, stream=False, ...)
    # Sync wrapper. Detects running event loop:
    #   Loop running → ThreadPoolExecutor + asyncio.run
    #   No loop → asyncio.run directly
```

## Event Types

```python
from agno.run.agent import (
    RunContentEvent,  # .run_id, .agent_id, .agent_name, .content
    ToolCallStartedEvent,  # .run_id, .agent_id, .agent_name, .tool (ToolExecution)
    ToolCallCompletedEvent,  # .run_id, .agent_id, .agent_name, .tool (ToolExecution)
)
from agno.run.base import RunStartedEvent, RunCompletedEvent, RunErrorEvent
# Terminal events are emitted by BaseExternalAgent._arun_stream; adapters must NOT yield them.
```

## ToolExecution

```python
from agno.models.response import ToolExecution

# Fields:
#   tool_name: str
#   tool_args: Dict[str, Any]
#   tool_call_id: Optional[str]
#   tool_call_error: Optional[str]
#   content: Optional[Any]          # result payload
#   metrics: Optional[Dict[str, Any]]
#   images: Optional[List[Dict]]
#   videos: Optional[List[Dict]]
#   audio: Optional[List[Dict]]
#   files: Optional[List[Dict]]
```

## AgentProtocol

```python
from agno.agent.protocol import AgentProtocol

# Satisfied by BaseExternalAgent via structural compliance, not inheritance.
# Key methods: get_id(), arun(), run(), print_response(), aprint_response()
```

## AgentOS Registration

```python
from agno.os import AgentOS

agent_os = AgentOS(
    agents=[hermes_agent, claude_agent, native_agent],
    tracing=True,
    db=SqliteDb(db_file="agentos.db"),
)
app = agent_os.get_app()
```

## Capability Matrix for External Agents

| Feature | External Agent | Notes |
|---------|---------------|-------|
| `AgentOS(agents=[...])` | ✅ | Adapters satisfy AgentProtocol |
| `/agents/{id}/runs` | ✅ | Same routes as native |
| SSE streaming | ✅ | Adapters emit events |
| Session persistence | ✅ | When `db` set on AgentOS |
| Standalone `.run()` | ✅ | Sync + async |
| Tool visibility in UI | ✅ | If adapter yields tool events |
| Team member | ❌ | Team orchestration is native-only |
| Memory | ❌ | Native Agent only |
| Knowledge | ❌ | Native Agent only |
| Guardrails | ❌ | Native Agent only |
| Structured I/O | ❌ | Use guest's native typing |
| Skills, reasoning, learning | ❌ | Native Agent only |

## Session Lifecycle Helpers (BaseExternalAgent)

```python
_create_session(session_id, user_id)  # builds AgentSession
read_or_create_session(...)  # sync DB fetch + fallback
aread_or_create_session(...)  # async DB fetch + fallback
upsert_session(...) / aupsert_session(...)  # write back with updated_at
```

These are used automatically by `arun()` / `run()` — adapters typically don't call them directly unless doing custom session manipulation.

## Terminal Output

`print_response()` / `aprint_response()` provide rich terminal formatting using `rich`:
- "Working..." spinner
- Message panel for user input
- Tool calls panel (accumulated in real time)
- Response panel with framework:name label
- Respects `self.markdown`
