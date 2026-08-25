---
name: hermes-external-integration
description: Patterns for integrating Hermes with external agent frameworks, runtimes, and observability platforms (e.g., Agno AgentOS, LangGraph control planes, custom trace UIs).
version: 1.0.0
author: Hermes Agent
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, integration, agents, observability, traceability, adapter, agno]
    homepage: https://github.com/NousResearch/hermes-agent
    related_skills: [hermes-agent, kanban-orchestrator, subagent-driven-development]
---

# Hermes External Integration

When you want Hermes sessions, traces, or execution to surface inside an external agent platform — whether for a nicer UI, shared observability, or unified API surface — use one of the three patterns below.

## Trigger Conditions

- The user wants Hermes runs visible in an external control plane or trace UI.
- The user wants to trigger Hermes from another agent framework's API or UI.
- The user is exploring "AgentOS", "LangGraph runtime", "CrewAI platform", or similar and mentions Hermes in the same breath.
- The user is replacing an existing observability backend (e.g., Agno AgentOS) with [Arize Phoenix](https://github.com/Arize-ai/phoenix) and needs instrumentation patterns.
- A need emerges to bridge Hermes's deep agent loop (skills, memory, delegation, cron) with a platform that has better visual traceability or production API endpoints.

## Pattern 1: External Agent Adapter (Tightest Integration)

Wrap Hermes as an adapter class that satisfies the target platform's external-agent protocol. The platform routes requests to Hermes, and Hermes's output is streamed back as native platform events.

### How it works
1. Implement the platform's external-agent base class (e.g., Agno's `BaseExternalAgent`).
2. In `_arun_adapter`, spawn Hermes in one-shot mode: `hermes chat -q <prompt>` or a PTY session for multi-turn.
3. Capture stdout/stderr, parse tool calls if the platform requires them, and map them to platform event types.
4. In `_arun_adapter_stream`, do the same but yield token-level events as they arrive.
5. Map the platform's `session_id` to a Hermes session ID so resume works across restarts.

### When to choose
- You want full platform features: SSE streaming, session persistence, API endpoints, approvals UI, trace tree/waterfall views.
- The platform already supports adapters for Claude SDK, LangGraph, etc. (proves the pattern works).
- You're willing to trade Hermes's interactive REPL feel for a request/response model (or build session resumption into the adapter).

### Pros
- Native traces, sessions, and UI rendering.
- Unified API surface alongside other agents.
- Platform handles auth, RBAC, and scaling.
- The control-plane UI can be self-hosted (see `references/agno-agent-os.md` → "Self-Hosted UI with Path Prefix" for the build-and-serve pattern behind reverse proxies) rather than relying on the hosted `os.agno.com` instance.

### Practical Serving Pattern
When self-hosting the UI alongside the runtime behind a reverse proxy (e.g., Tailscale `/agno`):
1. Build the AgentUI with `basePath: '/agno'` in `next.config.ts`
2. Mount `_next` static assets at root in FastAPI
3. Use `Accept: text/html` middleware to serve HTML for browsers while preserving JSON API responses
4. Inject an auto-connect script into `index.html` to set `localStorage.os-endpoint` to `window.location.origin`

See `references/agno-agent-os.md` for the full recipe, verification commands, and common pitfalls (307 redirect loops, asset 404s, localStorage caching).

### Cons
- Hermes loses its conversational REPL unless you engineer session resumption (see Pitfalls).
- Tool-call visibility depends on how well you parse Hermes's terminal output.
- Platform-native features (memory, knowledge, guardrails) won't work unless the platform explicitly supports them for external agents.

### Pattern 1b: Subprocess-Based Adapter (Hermes-specific reference)

When the target platform is Agno AgentOS and the guest is Hermes CLI, a production-validated adapter follows these rules:

1. **Always use quiet mode**: `hermes chat -q` (or `HERMES_QUIET=1`) suppresses TUI control sequences that pollute stdout capture.
2. **Map session IDs**: Maintain a bidirectional dict (`_hermes_session_ids`) from Agno `session_id` → Hermes session UUID. Parse `session_id: <uuid>` from stderr after each run. Pass `--resume <uuid>` on subsequent turns.
3. **Wrap subprocess in async**: Use `asyncio.to_thread()` around `subprocess.run` so the Agno event loop stays unblocked.
4. **Yield only content events**: `RunStartedEvent` / `RunCompletedEvent` / `RunErrorEvent` are owned by `BaseExternalAgent`. The adapter hook yields only `RunContentEvent` (and tool events if you can parse them). Raise on error; let the base class emit terminals.
5. **Tool calls are plain text**: Hermes quiet mode does not expose structured tool events. Accept that tool calls appear as prose in the response, or patch Hermes's tool registry to emit structured events.
6. **Environment propagation**: Ensure `HERMES_HOME` and `HERMES_CWD` are set in the subprocess env so the correct profile and working directory load.

Templates and protocol references:
- `templates/hermes_agent.py` — complete adapter class with session mapping, quiet mode, and error handling.
- `templates/agentos_registration.py` — bootstraps AgentOS + HermesAgent + uvicorn.
- `templates/test_adapter.py` — pytest suite mocking `subprocess.run` (never invoke real Hermes in tests).
- `references/agno-adapter-protocol.md` — condensed BaseExternalAgent API surface, event types, capability matrix.
- `references/hermes-agent-implementation.md` — real implementation notes from the validated HermesAgent adapter (quiet mode, session mapping, async bridge, testing strategy).

## Pattern 2: Trace Bridge (Pragmatic Middle Ground)

Keep Hermes running exactly as-is. Add a Hermes plugin that writes turn-level trace data into the external platform's database. The platform's UI reads from the same DB and renders Hermes sessions alongside native agents.

### How it works
1. Create a Hermes plugin (`~/.hermes/plugins/agno_trace/__init__.py`) that hooks into the conversation loop.
2. On each turn, write to the platform's trace tables (e.g., Agno's `AgentSession`, `Run`, and event tables).
3. The platform's control plane picks up the data automatically — no adapter needed.

### When to choose
- You want Hermes's interactive REPL, skills, and delegation to stay unchanged.
- The external platform stores all data in a database you control (Agno's "private by design" model, your own Postgres, etc.).
- You only need observability and debugging, not API-driven execution.

### Pros
- Zero change to Hermes UX.
- Read-only from the platform's perspective — no risk of breaking Hermes's loop.
- Can bridge multiple Hermes profiles into the same UI.

### Cons
- Write-only — the platform can display but not trigger Hermes runs.
- You must keep the DB schema in sync with platform releases.
- Session search and linking depend on schema stability.

## Pattern 3: Runtime Backend (Architectural Flip)

Use the external platform for its production API, auth, and control plane UI, but route actual agent execution to Hermes. The platform becomes a thin routing layer; Hermes is the brain.

### How it works
1. Deploy the platform's FastAPI runtime (or your own) with a custom endpoint backend.
2. On `/agents/{id}/runs`, instead of running a native agent, spawn a Hermes process or delegate to a running Hermes daemon.
3. Return SSE events by streaming Hermes's output back through the platform's event format.

### When to choose
- You need the platform's API contract and UI, but Hermes's toolset and skills are non-negotiable.
- You're building a product where the API surface matters more than the agent framework.

### Pros
- Best of both worlds: platform UI/API + Hermes capabilities.
- Can support interactive sessions if you keep a Hermes daemon alive per session.

### Cons
- Most invasive — custom backend code required.
- Session state lives in two places (platform DB + Hermes's SQLite).
- Higher operational complexity.

## Decision Guide

| Need | Choose |
|------|--------|
| Nice trace UI, no behavior change | Pattern 2 (Trace Bridge) |
| Full platform API + UI, OK with REPL loss | Pattern 1 (Adapter) |
| Product-grade API surface, must keep Hermes logic | Pattern 3 (Runtime Backend) |
| Quick win, low risk | Pattern 2 first, then Pattern 1 if you need API triggers |

## Pitfalls

1. **Session ID mapping is critical.** External platforms generate their own session IDs. You must maintain a bidirectional map (platform session ID ↔ Hermes session ID) or resumption breaks. Agno's `ClaudeAgent` does this with a `_sdk_session_ids` dict.
2. **PTY vs one-shot.** `hermes chat -q` is fire-and-forget. For multi-turn sessions inside an adapter, use tmux PTY sessions (see `hermes-agent` skill → Spawning Additional Hermes Instances). Raw PTY mode has `\r` vs `\n` issues with prompt_toolkit.
3. **Tool call visibility.** Hermes tools do not emit structured events by default. If the platform expects `ToolCallStartedEvent` / `ToolCallCompletedEvent`, you must either:
   - Parse terminal output (fragile), or
   - Patch Hermes's tool registry to emit structured events, or
   - Accept that tool calls show up as plain text in the trace.
   4. **Async/sync mismatch.** Hermes's CLI is synchronous. If the platform's adapter protocol is async, wrap Hermes in `asyncio.to_thread()` or `concurrent.futures.ThreadPoolExecutor`. Better yet, use a **persistent worker process** that stays alive across requests, eliminating Python interpreter cold-start (~1–2 s per message). See `references/agno-agent-os.md` → "Persistent Worker Pattern" and `templates/hermes_worker.py`.
   5. **Environment persistence.** Hermes relies on `~/.hermes/config.yaml`, `.env`, and skills. When spawning Hermes from an adapter, ensure `HERMES_HOME` is set correctly and the profile is loaded.
   6. **Gateway conflicts.** If Hermes's gateway is already running on the same machine, spawning additional Hermes processes for the adapter can compete for ports or DB locks. Use isolated profiles or `HERMES_HOME` overrides.
   7. **Missing database.** AgentOS requires a `db` parameter. Without it, endpoints like `/sessions` raise `StopIteration` because the OS cannot resolve a default database. Always pass `db=SqliteDb(...)` or `db=PostgresDb(...)` to `AgentOS(...)`. See `references/agno-agent-os.md` → "Database Expectations".
   8. **Direct LLM API calls strip tool access.** When building lightweight trigger processors (file watchers, vault scanners, webhook handlers) that need Hermes's full toolkit, always invoke `hermes chat -q` or delegate via `delegate_task` rather than calling the LLM API directly. A direct `requests.post` to `/chat/completions` produces plain text with zero tool access, no memory context, no file tools, no web search, and no gateway messaging (e.g., Slack). The model will truthfully report it cannot complete tasks that require those capabilities. See `references/file-trigger-integration.md` for the correct subprocess pattern and common mistakes.
   9. **Spawning Hermes without PATH inheritance fails.** When a parent process spawns Hermes with `subprocess.Popen(..., start_new_session=True)` (common for background daemons and file watchers), the child does not inherit the parent's `PATH`. The bare command `hermes` raises `FileNotFoundError`. Always use `_resolve_hermes_path()` (fallback to known absolute paths) instead of relying on `shutil.which("hermes")` alone. See `references/file-trigger-integration.md` → "Pitfall 2".
   10. **`--quiet` still emits a `session_id:` line.** `hermes chat -q --quiet` suppresses the TUI but prints `session_id: <uuid>` as the first line of stdout. If you write raw stdout into a response file, the session ID leaks into the external system. Strip the first line when it starts with `session_id:`. See `references/file-trigger-integration.md` → "Pitfall 3".
   11. **Hermes hangs on stdin in detached sessions.** When `process_trigger.py` is spawned with `start_new_session=True` (systemd, file watchers), Hermes `chat -q` blocks waiting for stdin input even though the prompt is passed as a CLI arg. The subprocess times out after 10 minutes with an empty response. Fix: pass `stdin=subprocess.DEVNULL` to `subprocess.run`. See `references/file-trigger-integration.md` → "Pitfall 4".
   12. **Trigger ID mismatch from absolute vs relative paths.** If the scanner hashes the absolute filesystem path (`/mnt/z/pantheon/vault/ZNH/Inbox/Note.md`) while the Obsidian plugin hashes the relative vault path (`Inbox/Note.md`), the generated IDs diverge and the instant processor cannot find the trigger in the log. Fix: use `filepath.relative_to(VAULT_PATH)` in the scanner's ID generation. See `references/file-trigger-integration.md` → "Pitfall 5".
   13. **Context loss in fresh sessions.** `hermes chat -q` spawns a brand-new Hermes session with zero memory, no conversation history, and no user profile. Responses feel generic ("I don't know who you are"). Fix: prepend a system-style user context block to every prompt. See `references/file-trigger-integration.md` → "Pitfall 6" for the exact template and what to include/exclude.

## Pattern 1c: Lightweight Trigger Integration (File Watchers, Vault Scanners)

A narrower variant of Pattern 1 for simple event-driven triggers from filesystem changes, vault edits, or webhook payloads where you don't need full platform API surface — just a response written back to a file or directory.

### How it works
1. An external watcher (e.g., Python `watchdog`, Obsidian plugin, cron) detects a change.
2. The watcher spawns Hermes in one-shot mode with the trigger content as the query.
3. Hermes runs with its full default toolset, writes its response, and exits.
4. The watcher captures the response and surfaces it in the external system.

### Why Hermes CLI over direct API
| Approach | Tool Access | Memory | File I/O | Web Search | Slack/Gateway |
|----------|------------|--------|----------|------------|---------------|
| `hermes chat -q` | ✅ Full | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Direct API call | ❌ None | ❌ No | ❌ No | ❌ No | ❌ No |

### Minimal implementation
```python
import subprocess
from pathlib import Path


def _resolve_hermes_path() -> str:
    import shutil

    path = shutil.which("hermes")
    if path:
        return path
    # Fallbacks for when PATH is not inherited (e.g. systemd, start_new_session)
    for p in [
        "/home/znh/.local/bin/hermes",
        "/mnt/z/pantheon/.hermes/hermes-agent/venv/bin/hermes",
    ]:
        if Path(p).exists():
            return p
    return "hermes"


def process_trigger(trigger_text: str, output_path: str) -> None:
    hermes = _resolve_hermes_path()
    result = subprocess.run(
        [hermes, "chat", "-q", trigger_text, "--quiet"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    output = result.stdout.strip()
    # --quiet still emits "session_id: <uuid>" on the first line — strip it
    lines = output.splitlines()
    if lines and lines[0].startswith("session_id:"):
        output = "\n".join(lines[1:]).strip()
    with open(output_path, "w") as f:
        f.write(output)
```

### When to choose
- You need instant/event-driven processing (sub-5-second response).
- The external system is file-based (markdown vault, local filesystem).
- You want visual feedback (e.g. CSS-driven status icons) in the external UI without polling Slack or another channel.
- You don't need platform traces, session trees, or REST API surface.

### When NOT to choose
- You need structured tool events in the external UI → use Pattern 1 with a full adapter.
- You need session resumption across multiple turns → use PTY mode (see `hermes-agent` skill).
- The external system expects JSON/SSE → use Pattern 3 (Runtime Backend).

## References

- `references/agno-agent-os.md` — Agno AgentOS specifics: BaseExternalAgent protocol, ClaudeAgent reference implementation, persistent worker pattern, streaming implementation, DB requirements, performance tuning, and the full self-hosting recipe with common pitfalls.
- `references/phoenix-otel-instrumentation.md` — Arize Phoenix OTEL instrumentation patterns: lazy tracer initialization, no-op fallback, API traps (`span.end()` vs `span.__exit__()`, `set_attribute` vs `set_attributes`), and safe per-layer instrumentation recipes for worker pools, schedulers, and agent trackers.
- `references/file-trigger-integration.md` — Event-driven Hermes triggers from file-based systems (Obsidian vaults, markdown scanners, webhook-to-file handlers). Covers the correct subprocess pattern, PATH resolution, quiet-mode output cleanup, visual `data-status` feedback, theme-compatible CSS recipes, and the context-loss pitfall with the prepend-context workaround.
- `templates/external-agent-adapter.py` — Production-ready adapter with persistent worker and real-time streaming.
- `templates/hermes_worker.py` — Standalone persistent worker that stays alive across requests.

## Related Skills

- `hermes-agent` — Hermes setup, spawning, CLI reference, and PTY patterns.
- `kanban-orchestrator` / `kanban-worker` — If the integration spans multiple Hermes profiles coordinated through work queues.
- `subagent-driven-development` — If Hermes delegation patterns are part of the architecture.