# Agno Feature Architecture

This reference covers the specific split between open-source and hosted
features in Agno, as discovered during a live audit of the user's setup.

## Architecture Layers

| Layer | Package | License | What it does |
|-------|---------|---------|--------------|
| SDK | `agno` | Apache 2.0 | Build agents, teams, workflows, memory, tools, knowledge. |
| Runtime | `agno[os]` | Apache 2.0 | FastAPI service. Sessions, traces, RBAC, scheduling, APIs. Stores data in YOUR database. |
| Control Plane | `os.agno.com` | Free for local OS | Web UI: Studio (visual builder), Tracing (tree/waterfall), Chat, Session manager, Knowledge/Memory UIs, Scheduler, Approvals. |

## What is NOT in the open-source package

- **Studio** — visual drag-and-drop agent builder
- **Trace viewer** — tree view and waterfall view of execution spans
- **Session manager** — browse, filter, inspect conversation history
- **Knowledge UI** — manage RAG knowledge bases
- **Memory UI** — view/edit user memories
- **Scheduler UI** — cron job management

These are all part of the **hosted Control Plane**.

## What IS in the open-source package

- All backend APIs that the Control Plane consumes (50+ endpoints)
- SQLite/Postgres storage for sessions, traces, metrics, memories
- OpenTelemetry tracing hooks
- JWT-based RBAC
- SSE and WebSocket streaming

## User's Setup

- **Runtime:** `agent_context/scripts/serve_agno.py` in `purple-phoenix/main`
- **Host:** `127.0.0.1:9120`
- **Tailscale:** `/agno` proxies to `http://127.0.0.1:9120`
- **Static UI:** `agent_context/static/agent-ui` — this is ONLY a chat template (Next.js), not the Control Plane.

## How to access Studio/Tracing

1. Go to `https://os.agno.com` in a browser.
2. Add your AgentOS endpoint: either `http://localhost:9120` (local) or
   `https://<tailnet-host>/agno` (Tailscale).
3. The Control Plane connects **directly** from your browser to your runtime.
   No data is sent to Agno servers.
4. Studio, Tracing, Sessions, etc. will now be available.

## Self-hosting the Control Plane

Requires **Enterprise** plan. Agno does not open-source the full Control
Plane UI. The only self-hosted UI in the open-source repo is the chat
template.
