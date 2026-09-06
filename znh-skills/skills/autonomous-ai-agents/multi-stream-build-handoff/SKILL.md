---
name: multi-stream-build-handoff
description: Clarify, then dispatch a design+build+DB brief to OpenCode.
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [delegation, handoff, opencode, design, build, database, planning]
    related_skills: [opencode-worker, external-coding-agents, task-dispatch, using-pantheon-mcp]
---

# Multi-Stream Build Handoff

Use when a brief spans **design + frontend build + database** and must be
handed to an autonomous coding agent (OpenCode). A wrong assumption here is
expensive — a long-headed agent run built on the wrong stack or wrong build
location wastes the whole run. Run a clarification pass FIRST, then assemble
a self-contained override file for the agent.

## The clarification pass (ask before dispatching)

Four decisions genuinely need the user. Confirm each before writing the
handoff — do not assume any of them.

1. **Backend conflict.** A written brief may spec one DB while the user's
   verbal instruction names another (real case 2026-08-08: brief said
   PocketBase, user said Supabase). These stacks are materially different
   (local SQLite + built-in admin/review UI vs hosted Postgres). Surface the
   conflict and let the user pick. NEVER silently prefer the verbal
   instruction OR the written brief — name the conflict outright.

2. **Where "finish the design" happens.** In a design-heavy task, the agent
   either (a) finishes the design in the source-of-truth design tool (Figma)
   via MCP, design-first then build, or (b) designs natively in code from the
   token/design system spec. Ask. The user often wants design-in-Figma first.
   This changes the whole workstream (Figma MCP work vs pure CSS/Astro).

3. **Build target directory.** In a Pantheon project this is critical:
   `main/` is a READ-ONLY reference worktree (AGENTS.md says editing it
   "breaks the running tool") and is often empty for greenfield work. The
   canonical write zone is `tasks/NNN-slug/`. Confirm the destination, set
   the agent's `workdir` there, and NEVER let the agent write to `main/`.

4. **Assumed-but-missing assets.** Flag when the brief's requirements
   reference a previous site that isn't in the repo (e.g. "301-redirect old
   article URLs", "carry forward the 5 existing articles"). Surface this to
   the user rather than letting the requirement silently go unmet, and note
   it to the agent so it doesn't hallucinate the missing content.

## Before dispatching: verify the agent can reach its MCP claims

If the task depends on an MCP (e.g. Figma), verify the server is actually
registered in the agent's config at dispatch time. In these environments
OpenCode has NO dedicated `figma` MCP — Figma is reached through the
`pantheon` MCP hub (`mcp.pantheon` already present in OpenCode's global
`~/.config/opencode/opencode.json`; confirm the block exists before promising
file access). See the `using-pantheon-mcp` skill for the exact
search → get_schema → execute pattern and sandbox restrictions (no
`import`, no `print`, `get_schema(tools=[...])` takes a LIST).

## Assemble MAIN_INSTRUCTIONS.md (in the task dir)

Write ONE file inside the target task directory (not in `main/`):

- (a) Points at the requirements brief by filename.
- (b) Lists the handoff decisions as **highest-priority overrides** (explicit:
  "override the brief where they conflict").
- (c) States the delivery order — design → schema → build → seed → wire →
  verify — and the non-goals (what NOT to build).
- (d) States the working boundary (e.g. "root: this dir, do not touch
  `../main/`") and verification expectations for the final summary.

Copying the brief INTO the task dir also avoids the sandbox's
external-directory read rejection.

## Dispatch

```python
terminal(
    command="opencode run --auto 'Do X per the attached instructions...' -f MAIN_INSTRUCTIONS.md --title <name>",
    workdir="/path/to/projects/<proj>/tasks/NNN-slug",
    background=True,
    pty=True,
    timeout=600,
    notify_on_complete=True,
)
```

Message positional comes BEFORE `-f` (on OpenCode 1.18.x, `-f` before the
message makes OpenCode parse the message as a file path). DB work may run as
a parallel dispatch stream if independent of the design/build work — but
still needs decision #1 (backend) settled first.

## Pitfalls

- **Dispatching blind** on a design+build+DB brief: you'll build the wrong
  DB or the wrong location. Always clarify the 4 decisions first.
- **Using `main/` as the build root** in a Pantheon project: it's read-only
  reference. Point workdir at `tasks/NNN-slug/`.
- **Trusting the brief over a live user instruction, or vice versa**, when
  they conflict on stack — ask.
- **Promising Figma access** without confirming the `pantheon` MCP is
  registered in the agent's config.
- **Embedding the long brief inline** in the shell command — bash spoils
  multi-line prompts. Write MAIN_INSTRUCTIONS.md and pass `-f`.
