---
name: external-coding-agents
description: "Delegate coding tasks to external CLI agents: Claude Code, OpenAI Codex, and OpenCode."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [coding-agent, delegation, claude, codex, opencode, cli, pty]
    related_skills: [hermes-agent, opencode-worker, kanban]
---

# External Coding Agents

Delegate coding tasks to autonomous CLI coding agents. Three tools are covered here — pick the one the user has installed or prefers.

| Tool | Install | Best For | Auth |
|---|---|---|---|
| **Claude Code** | `npm install -g @anthropic-ai/claude-code` | Large refactors, deep reasoning, multi-file changes | `claude auth login` (OAuth / API key / SSO) |
| **OpenAI Codex** | `npm install -g @openai/codex` | Quick fixes, OpenAI ecosystem | `OPENAI_API_KEY` env or `openai` CLI login |
| **OpenCode** | Platform-specific installer | General coding, Hermes ecosystem integration | `opencode auth` or env keys |

## Shared Orchestration Patterns

All three tools support the same two modes:

### 1. One-shot mode

Fire-and-forget for tasks that can complete in one go:

```bash
claude --no-prompts -p "Fix the JWT validation bug in auth.py"
```

```bash
codex --no-prompts -p "Add rate limiting to the API"
```

```bash
opencode run "Implement the NerdFont icon library per PLAN.md"
```

Use `--dangerously-skip-permissions` with OpenCode for headless runs (auto-approves external directory reads).

### 2. Interactive PTY mode

For tasks that need iteration, clarification, or multi-step exploration:

```python
terminal(command="cd /path/to/project && claude --verbose", pty=True, timeout=600)
```

```python
terminal(command="cd /path/to/project && codex --model o4-mini", pty=True, timeout=600)
```

```python
terminal(
    command="cd /path/to/project && opencode run '<detailed task>'",
    pty=True,
    timeout=600,
)
```

PTY mode allows the agent to handle its own iteration loop, view tool outputs, and ask follow-up questions interactively.

## Tool-Specific Details

### Claude Code

- **Version check:** `claude --version` (needs v2.x+)
- **Health check:** `claude doctor`
- **One-shot flags:** `--no-prompts -p "<prompt>"`
- **Model override:** `claude --model claude-sonnet-4-20250514`
- **Safety:** `--no-approval` for non-interactive; `--approval-mode full` requires confirmation per tool call
- **Git integration:** Claude manages its own branching and commits. If you need to stay on a specific branch, tell it explicitly: "Stay on branch `feature/x`, do not create new branches."
- **Subagent spawning:** Claude can spawn its own subagents. If you already have a subagent architecture, tell it: "Do not spawn subagents."
- **Timeouts:** Default is 600s. Complex tasks may exceed this — chunk them or use PTY mode.

### Codex

- **Version check:** `codex --version`
- **One-shot flags:** `--no-prompts -p "<prompt>" --model o4-mini`
- **Context:** Codex has a 200k token context window. It can ingest large codebases in one shot.
- **Safety:** Codex has an approval system. Use `--no-approval` for non-interactive runs.
- **Git integration:** Codex handles git operations automatically. Constrain it if needed: "Do not commit or push."

### OpenCode

- **Install:** Platform-specific (check `opencode --version`)
- **One-shot:** `opencode run "<task>"`
- **Auto-approve permissions:** `opencode run --dangerously-skip-permissions "<task>"` (essential for headless/agent sessions)
- **Pantheon integration:** When working inside a Pantheon task directory, prefer `pantheon task supervise` over raw `opencode run`. It reads `TASK-BRIEF.md`, generates an implementation queue, and handles the Junior/Senior audit pipeline.
- **External directory reads:** OpenCode auto-rejects reads outside the project tree. Copy referenced files into the working directory first, or inline brief content in the task string.
- **Task style:** State the problem and desired outcomes, not implementation steps. OpenCode figures out the approach.

## Common Pitfalls (All Tools)

- **Version too old:** Always check `--version` first. Old versions may lack features or have different flags.
- **Auth missing:** Run auth/login before any task. Check `auth status`.
- **Wrong working directory:** Always `cd` into the project root before invoking the agent.
- **Timeout on large tasks:** Break into smaller chunks or use PTY mode for open-ended work.
- **Git branch surprises:** Explicitly tell the agent which branch to use and whether it's allowed to create new branches or commit.
- **Over-specifying:** Give the problem and constraints, not step-by-step implementation plans. The agent reasons better with goals than with scripts.
- **Subagent conflicts:** If you already use `delegate_task` or Kanban workers, tell the coding agent not to spawn its own subagents to avoid nested delegation loops.

## When to Use Which

- **Claude Code** → deepest reasoning, largest context, best for architectural refactors and complex multi-file changes.
- **Codex** → fast, OpenAI-native, great for quick fixes and when the team already uses OpenAI models.
- **OpenCode** → best Hermes integration, Pantheon task supervision, and when the user explicitly prefers it.

## Related Skills

- `opencode-worker` — Hard-rule worker skill that mandates ALL code changes go through OpenCode.
- `kanban` — If coding tasks are part of a multi-agent board workflow.
- `hermes-agent` — Hermes setup, spawning, and PTY patterns.
