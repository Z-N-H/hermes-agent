---
name: tool-feature-audit
title: Tool Feature Audit
version: 1.0
description: >
  Audit a locally-installed open-source tool to determine which features are
  available, which require paid tiers, and how the project's architecture splits
  between SDK, runtime, and UI layers.
trigger: >
  - User asks "are X and Y paid features?"
  - User asks whether a tool supports a specific capability
  - Checking why installed software does not show expected features
  - Comparing local installation to latest upstream version
---

# Tool Feature Audit

## Goal
Determine exactly what features are present in the local install, what is
available upstream, and what is gated behind paid/hosted tiers.

## Audit Steps

### 1. Check what is installed
```bash
python3 -c "import <pkg>; print(<pkg>.__version__)"
# or
pip list | grep -i <pkg>
```
If the package is inside a venv or uv tool, use the correct Python binary.

### 2. Check PyPI for latest
```bash
pip index versions <pkg>
```
Compare installed vs latest. If outdated, offer upgrade.

### 3. Check what is actually running
```bash
ss -tlnp | grep <port>
lsof -i :<port>
ps aux | grep <process>
curl -s http://localhost:<port>/health
```
Confirm the service is live and reachable.

### 4. Examine integration / wrapper code
Read the project's wrapper script (e.g., `serve_agno.py`) to see how the
library is instantiated. Check whether optional extras are imported
(e.g., `agno[os]`, tracing instrumentation). Look at static asset directories
to see what UI is being self-hosted vs delegated to a hosted control plane.

### 5. Research the official architecture
Search the project's docs for:
- "Pricing" page — lists free vs paid tiers explicitly
- "Introduction" or "Architecture" page — shows how SDK / runtime / UI split
- Docs for the missing feature (e.g., `/monitoring`, `/tracing`, `/studio`)
  — may 404 or redirect if not part of the open-source package

Key distinction to map:
- **SDK / library features** — usually fully open source
- **Runtime / server features** — usually fully open source
- **Web UI / Control Plane** — often hosted-only in free tier; self-hosted
  may require Enterprise. Watch for static files that are *just* a chat
  template vs a full admin dashboard.

### 6. Report clearly
Present findings as a table:

| Feature | Local? | Free? | Notes |
|---------|--------|-------|-------|
| ...     | ...    | ...   | ...   |

If a feature requires connecting to a hosted control plane, give the exact
URL and explain the data-privacy model (browser-direct-to-local vs
cloud-stored).

## Agno-Specific Reference

Agno's architecture:
- `agno` (SDK) — open source. Agents, teams, workflows, memory, tools.
- `agno[os]` (AgentOS runtime) — open source. FastAPI backend with tracing
  storage, session persistence, RBAC, scheduling. Runs entirely locally.
- **Control Plane** (`os.agno.com`) — hosted web UI. Free to connect to a
  local AgentOS. Self-hosting requires Enterprise.
- The static `agent-ui` files shipped in some project templates are a
  lightweight chat interface only; they do NOT include Studio, trace
  waterfall views, or knowledge management.

To see Studio/Tracing with a local AgentOS, connect the hosted Control
Plane to your runtime endpoint (`http://localhost:9120` or your Tailscale URL).

## Pitfalls
- Do not assume a missing UI means a missing backend. Traces may be stored
  in the local database but only viewable through the hosted Control Plane.
- Do not assume all static files in a project repo constitute the full product.
  Check official docs for what the self-hosted bundle actually includes.
- When checking PyPI, use `pip index versions` rather than `curl` to the
  JSON API — the latter may be blocked by security policies.
