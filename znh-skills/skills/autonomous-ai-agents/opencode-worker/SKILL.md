---
name: opencode-worker
description: Delegate all coding tasks to OpenCode CLI. Ensures no code is written directly by Hermes - all implementation, refactoring, debugging, and code review goes through OpenCode.
version: 2.1.0
platforms: [linux, macos, windows]
environments: [hermes]
metadata:
  hermes:
    tags: [opencode, coding, delegation, agent]
    related_skills: [hermes-agent]
---

# OpenCode Worker — Code Delegation Skill

> **⚠️ CRITICAL BOUNDARY — ZERO EXCEPTIONS**: You are an orchestration and delegation agent ONLY. You MUST NEVER write, edit, patch, modify, create, read, or investigate code files yourself — NOT EVER. This includes patch, write_file, terminal sed/awk, cat/grep/head on source files, or any direct code modification or inspection tool. ALL coding tasks — writing, reading, debugging, code review, refactoring, investigating bugs — MUST be delegated to OpenCode via `opencode run` or PTY mode. Your role is strictly assistance, orchestration, and delegation. When a coding task arises, give a clear brief of the problem and the desired outcome, but DO NOT investigate, diagnose, read, or solve code problems yourself. **Even "just one peek at the file" is forbidden.**

> **⚠️ `--auto` IS MANDATORY**: Every `opencode run` delegation MUST include the `--auto` flag (e.g. `opencode run --auto "<task>"`). Without `--auto`, OpenCode prompts for permission on every file write — but those prompts are invisible inside PTY/background terminal sessions. The agent reads files, plans changes, then silently stalls and exits with no writes. This was the root cause of 5+ consecutive failed delegations. **Never omit `--auto`.**

## Hardening the Boundary Beyond Memory

Memory is soft — it gets injected into context but can be overridden by model training or other prompt content. When a user says a boundary "needs to be firmer than a memory" or "in your initial prompt," there are two approaches, ordered by hardness:

### Approach A: Source-level system prompt patch (hardest, most durable)

Patch the Hermes source directly to prepend the boundary to the **stable tier** of the system prompt. This survives config changes, new sessions, gateway restarts, and model switches. It lives in the prompt builder constants, not user config.

**Files to modify** (under `~/.hermes/hermes-agent/` or `$HERMES_HOME/hermes-agent/`):
- `agent/prompt_builder.py` — add the boundary as a Python string constant
- `agent/system_prompt.py` — import and prepend it to `stable_parts` as the very first block, before identity/SOUL.md

**Why this is the strongest approach:**
- The stable tier is built once per session and reused across every turn
- It sits **before** identity, skills, environment hints, and all other guidance
- It cannot be compressed out of context or overridden by SOUL.md/AGENTS.md
- It survives `hermes config edit`, profile switches, and gateway restarts
- It is present in the system prompt on every API call

**Example:**
```python
# agent/prompt_builder.py
CRITICAL_BOUNDARY_GUIDANCE = (
    "CRITICAL BOUNDARY: You are an orchestration and delegation agent only. "
    "You must NEVER write, edit, patch, modify, or create code files yourself. "
    "All coding tasks MUST be delegated to OpenCode via `opencode run` or PTY mode. "
    "Using patch, write_file, terminal sed/awk, or any direct code modification tool "
    "on behalf of a user is FORBIDDEN."
)

# agent/system_prompt.py
from agent.prompt_builder import CRITICAL_BOUNDARY_GUIDANCE


def build_system_prompt_parts(agent, system_message=None):
    stable_parts = []
    # Hard-coded critical boundary — must never be bypassed or missed.
    stable_parts.append(CRITICAL_BOUNDARY_GUIDANCE)
    # ... rest of stable_parts assembly
```

**Trade-off:** Requires editing source. The change is global to all Hermes sessions on this machine. To make it profile-specific, wrap in a conditional check.

### Approach B: `agent.system_prompt` config (softer, user-configurable)

Hermes appends `agent.system_prompt` from `config.yaml` to the base system prompt on every API call as the `ephemeral_system_prompt`:

```bash
hermes config set agent.system_prompt "Your boundary text here"
```

**Mechanism:**
- The gateway reads this at startup (`gateway/run.py::_load_ephemeral_system_prompt`).
- The CLI reads it at init (`cli.py`).
- It is injected in `chat_completion_helpers.py` and `conversation_loop.py` by appending to the effective system prompt.
- `HERMES_EPHEMERAL_SYSTEM_PROMPT` env var takes precedence over config.

**Why this works:** The boundary lives in the system prompt itself, not in the conversation history or memory store. It is present on every turn and cannot be "forgotten" mid-session. It also survives gateway restarts and new sessions automatically.

**Why it's softer than source-level:**
- It lives in user config, which can be edited or reset
- It is appended, not prepended — later in the prompt than source-level constants
- It can be overridden by `HERMES_EPHEMERAL_SYSTEM_PROMPT` env var
- It doesn't survive `hermes update` reinstallation of source

**Example — the orchestration boundary:**
```bash
hermes config set agent.system_prompt "You are an orchestration agent, not an individual contributor. ALL coding-related work — including writing code, debugging errors, planning implementations, investigating bugs, code review, and refactoring — MUST be delegated to OpenCode. Your role is strictly assistance, orchestration, and delegation. When a coding task arises, give a clear brief of the issue and what is happening, but DO NOT investigate, diagnose, or solve code problems yourself. Zero exceptions."
```

Restart the gateway (`/restart` in chat, or `hermes gateway restart`) for changes to take effect in messaging platforms. CLI sessions pick it up on the next `/reset` or new `hermes` invocation.

## When to Use

- Any task involving: writing code, editing files, refactoring, debugging, code review, writing tests, fixing bugs
- Any task where the output is source code, config files, scripts, or infrastructure-as-code
- User explicitly says "use opencode" or "code this"

## How It Works

This skill provides `opencode_delegate` tool that:
1. Takes a coding task description
2. Runs `opencode run "<task>"` in the project directory
3. Returns OpenCode's output (summary, files changed, test results)

## Tool: opencode_delegate

```python
opencode_delegate(
    task: str,           # What OpenCode should do
    workdir: str = ".",  # Working directory (absolute path)
    model: str = None,   # Optional model override
    timeout: int = 600   # Seconds (default 10 min)
) -> str
```

## PTY vs Python `opencode_delegate` tool

There are two ways to invoke OpenCode. Choose based on task complexity:

### 1. Python `opencode_delegate` tool — good for script-gen, risky for focused edits

Use the `opencode_delegate` Hermes tool when the task is creating new files
(especially from exact-content inline) or running self-contained code generation.
It handles prompt passing cleanly and has no bash quoting issues:

```python
opencode_delegate(
    task="Write a stdlib-only Python heartbeat script...", workdir="/path/to/project"
)
```

**However, `opencode_delegate` has a failure mode that PTY mode doesn't:**
OpenCode may read the target files, then go off on a tangent — globbing for
unrelated files (TASK-BRIEF.md, *-task.md, etc.) across the entire repo —
instead of doing the actual edit. The glob can find 50+ matches and fill its
context with noise, producing zero output or returning early. This is a
tool-internal breadth-exploration issue, not a prompt quality issue.

**When to prefer PTY mode over opencode_delegate:**
- Editing existing files (not creating new ones)
- The task touches 2-3 existing files with specific edits (add function + wire call + add CSS)
- You observe opencode_delegate read the target files then produce no output

```python
opencode_delegate(task="Fix the login bug in auth.py", workdir="/path/to/project")
```

**Verified 2026-07-28:** Wrote a 248-line Python module with multiple functions,
imports from sibling modules, and a full CLI, then ran verification — all via
`opencode_delegate` on a single call. The PTY `opencode run` approach failed
repeatedly on the same task due to CLI argument parsing issues.

**Limitations** (discovered 2026-06-20):
- **External directory permissions**: The tool auto-rejects reads outside the
  project tree. Copy plans/specs into the working directory first.
- **600 s timeout ceiling**: Complex multi-file refactors can exceed this.
  The tool will silently timeout even if OpenCode is still working.

### 2. PTY mode (`opencode run`) — complex / multi-file tasks
Use for large refactors, feature implementation, or anything touching >3 files:

```bash
cd /path/to/project
opencode run "Implement the NerdFont icon library per PLAN.md"
```

In Hermes, use `pty=true` on the `terminal()` call so OpenCode can run
interactively and stream output. Pass the project directory via the
`workdir` param on `terminal()` — do NOT also `cd <path> &&` inside the
command string, and do NOT append the path as a trailing bare argument
after the task message:

```python
terminal(
    command="opencode run --auto '<detailed task>'",
    workdir="/path/to/project",
    pty=True,
    timeout=600,
)
```

**Pitfall — trailing positional path corrupts the prompt:** `opencode run`'s
message positional is declared `[array]` in its CLI (see `opencode run --help`).
Any bare argument after the task string — e.g.
`opencode run --auto -- "task" /path/to/project` — gets silently absorbed
into that array and joined onto the task text as literal prompt content.
OpenCode then receives `"task /path/to/project"` as one garbled message,
gets confused about what's being asked, and often produces no code changes
at all (exit 0, no writes). The project directory belongs in exactly one
place: the `workdir` param on `terminal()`.

PTY mode has no external-directory restriction and allows OpenCode to handle
its own iteration loop without hitting the Python wrapper's timeout.

**Auto-approving permissions** (OpenCode 1.18.x uses `--auto`; older versions used `--dangerously-skip-permissions`):  
OpenCode prompts for permission on each external-directory read. For long
autonomous runs where you want OpenCode to explore freely, add the appropriate
flag to the `opencode run` command to auto-approve reads that are not explicitly
denied:

```bash
# OpenCode 1.18.x (current on this system — check with `opencode --version`)
cd /path/to/project && opencode run --auto '<task>'

# OpenCode 1.16.x and earlier (deprecated flag name)
cd /path/to/project && opencode run --dangerously-skip-permissions '<task>'
```

**--dangerously-skip-permissions is version-dependent**: The `--dangerously-skip-permissions` flag was removed in OpenCode 1.18.x (does not appear in `--help` output). Using it with 1.18.x may silently fail or be ignored. Verify available flags with `opencode run --help` before relying on version-specific options. The replacement is `--auto`, which auto-approves all permissions.

Only use these flags in trusted directories where you want OpenCode to run
unattended without stopping for permission requests.
When working inside a Pantheon task directory, **always** use the built-in supervision framework:

```bash
pantheon task supervise
```

This reads `TASK-BRIEF.md`, generates an implementation queue, and dispatches
OpenCode via `cli_wrappers.py` with diff-based promotion. It also handles the
Junior/Senior audit pipeline automatically.

**Pitfall:** Running `opencode run` directly inside a Pantheon task bypasses the
queue generator, prompt builder, and oversight framework. The result is often
off-track work that doesn't respect the brief's constraints.

**Mitigation:** Always prefer `pantheon task supervise` over raw `opencode run`
when a Pantheon task directory is available.
**PTY mode caveat — external-directory reads still blocked:** OpenCode's own tool system auto-rejects reads outside the project tree even in PTY mode. The rejection manifests as `! permission requested: external_directory (...) ; auto-rejecting`. This is NOT a Python-wrapper restriction — it's OpenCode's internal sandbox. **Workaround:** Copy any referenced files (task briefs, plans, specs) into the working directory before delegating, or inline the brief content directly in the task string.

**Pantheon task delegation pattern:** Pantheon task briefs live in `tasks/<id>/TASK-BRIEF.md` while work happens in `main/`. Before delegating, copy the brief into the working directory:
```bash
cp tasks/266-unified-pantheon-semantic-search/TASK-BRIEF.md main/TASK-BRIEF-266.md
cd main && opencode run "Read TASK-BRIEF-266.md and implement..."
```
its own iteration loop without hitting the Python wrapper's timeout.

## Usage Pattern

```python
# Simple fix — Python wrapper is fine
result = opencode_delegate(
    task="Fix the login bug in auth.py - JWT validation fails on expired tokens",
    workdir="/path/to/project",
)

# Complex refactor — use PTY mode instead
terminal(
    command="opencode run --auto 'Rewrite hermes_icons.py with a lookup class, add tests, verify with pytest'",
    workdir="/path/to/project",
    pty=True,
    timeout=600,
)
```

## Task Description Style — PRD Format

**User preference: PRD-style briefs.** Give the problem in a structured format, not the solution. OpenCode is capable of working out implementation details from a clear problem statement. Over-specifying steps (exact file paths, line numbers, code snippets, commands) constrains its reasoning and leads to bash-parsing errors or corrupted task strings.

Use this four-section format:

1. **Context** — What exists, architecture background, relevant files (briefly — let OpenCode read them).
2. **What the issue is** — The problem to solve. Observable symptoms, broken behaviour, gap in functionality.
3. **Intended behaviour** — How things should work after the change. Concrete but implementation-agnostic.
4. **Acceptance criteria** — Verifiable conditions that define done. What passing looks like.

**Good brief (PRD format):**
> **Context:** A unified semantic search index exists at `/mnt/z/pantheon/.cocoindex_code/` that spans our monorepo. It was built for code search and lacks project-scoped filtering.  
> **Issue:** Searching across the entire index mixes results from different projects, causing context bleed for agents working on a single project.  
> **Intended behaviour:** Search should return results scoped to the active project by default, with an optional toggle to search across all projects. File paths should strongly influence relevance scoring.  
> **Acceptance criteria:** Searching with an active project only returns chunks from that project's directory. The vault toggle excludes/includes vault paths. CLI subcommand matches existing `main/` patterns.

**Bad brief (over-specified):**
> "Step 1: run `ccc init` at `/mnt/z/pantheon`. Step 2: write a function `pantheon_search(query, active_project)` that calls `subprocess.run(['ccc', 'search', ...])`. Step 3: parse output with regex `/File: (.+)/`. Step 4: ..."

The PRD format states goals, constraints, and acceptance criteria without dictating implementation. OpenCode reads the relevant files and figures out the rest.

**Bash-quoting safety:** Never include backticks, `$()`, `{}` with f-strings, or multi-line Python code blocks in the task string passed to `opencode run "..."`. Bash interprets these before OpenCode sees them, causing syntax errors and corrupted task briefs. If the PRD requires code examples or paths with special characters, write the brief to a file and use `opencode run "..." -f BRIEF.md` instead of inlining it.

**Don't over-specify implementation (line numbers, code snippets, commands):** Including exact line numbers, code to paste, or shell commands in the brief causes two problems: (1) bash parses fragments as commands and throws syntax errors before OpenCode sees the brief; (2) the model's reasoning is constrained — it follows your exact instructions even when they miss the real issue. State the problem and desired outcome. Let OpenCode find line numbers and write the code. Verified 2026-07-29: 5 delegations with line-number-exact instructions all failed; 1 delegation with a PRD-style problem statement landed cleanly.

## Model Configuration

OpenCode has its own model/provider config separate from Hermes. The default
model is determined by:

1. **`opencode.json`** at `~/.config/opencode/` (global) or `<project>/opencode.json`
   (project-level override). Only the global config typically specifies providers
   and models; project-level configs usually only set LSP or MCP settings.

2. **Provider and model fields** in `opencode.json` — the config contains a
   `provider` dictionary with named provider entries, each listing available
   models. If no `defaultModel` or `model` is set at the root level, OpenCode
   uses the **first model from the first provider** in the dictionary.

3. **The `--model` flag** on `opencode run` overrides the default per-task:
   ```bash
   opencode run --auto --model synthetic/hf:zai-org/GLM-5.2 "<task>"
   opencode run --auto --model openrouter-nitro/z-ai/glm-5:nitro "<task>"
   ```

### Discovering the active model

If the default isn't explicit in the config file, confirm by checking the
`opencode.json` provider order:

```python
cat ~/.config/opencode/opencode.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
for pname, pdata in d.get('provider', {}).items():
    models = list(pdata.get('models', {}).keys())
    print(f'{pname}: {models[0] if models else \"(no models)\"}')
"
```

The first listed model is OpenCode's default. To verify what model a running
instance is using, check the `> build · hf:...` banner in its output — that's
the model init line and includes the model id.

### Model restrictions relevant to delegation

- **Context window** — each model has a context limit (e.g. GLM-5.1 = 128K,
  GLM-5.2 = 512K, GLM-5 Nitro = ~200K). Large tasks with extensive briefs
  or many referenced files can exceed this, causing the model to forget
  earlier instructions.
- **Tool-call support** — some models listed in the config (`reasoning: true`)
  may not have reliable tool-calling. If OpenCode reads files but produces
  no edits, the model may be silently failing tool execution — try a
  different model via `--model`.
- **Output limit** — most models cap output at ~4K tokens. Very long code-gen
  tasks (multi-file scaffolding, 500+ line files) may need multiple passes.

OpenCode must be installed and authenticated:
- `opencode --version` works
- `opencode auth` configured (or OPENAI_API_KEY/ANTHROPIC_API_KEY in env)

The skill auto-detects the project root by looking for `.git`, `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, or `opencode.json`.

## Reference Files

- `references/delegation-patterns.md` — Concrete examples of good vs bad delegation for 8 common scenarios. Read this when you're unsure how to handle a code-related request.
- `references/secretary-snr-engineer-analogy.md` — Full transcript and rationale for the "you are a PM, not an engineer" behavioural model. Read this if you find yourself investigating before delegating.
- `references/pantheon-task-worktrees.md` — How Pantheon task worktrees work and how to launch OpenCode correctly.
- `references/tool-name-confusion.md` — Why `opencode_run` is not a Hermes tool and the correct terminal invocation patterns.
- `references/file-flag-ordering.md` — The `--file` flag argument ordering pitfall discovered on OpenCode 1.18.x (message before `-f`) and the PTY silent-no-output workaround using `delegate_task`.
- `references/hybrid-dispatch-patterns-2026-07-29.md` — Decision matrix for choosing `opencode_delegate` vs PTY mode, with verified examples (ccc-search plugin, systemd files outside project tree).
- `references/server-client-plugin-architecture.md` — Pattern for building HTTP bridges when server-side tools (ccc, API keys) live on a different machine than the Obsidian app. Use when a plugin needs CLI/database access across machines.

## Behavioural Model: You Are the Project Manager, Not the Senior Engineer

Your role is delegation and facilitation, not implementation. The analogy to internalise:

**You are a secretary or project manager. OpenCode is the senior software engineer.**
When a coding problem arises, your job is to brief the senior engineer and step out of their way. You do NOT:
- Investigate the problem yourself before handing it off
- Read the code to understand the context before delegating
- Propose implementation steps or constrain the approach
- Debug, trace, or hypothesise about root causes

The senior engineer is stronger than you at coding. Let them do their job.
A project manager who starts directing the engineer on implementation details is meddling, not helping.

**How this manifests in practice:**

| Situation | What NOT to do (meddling) | What to do (delegate) |
|-----------|--------------------------|----------------------|
| Bug report comes in | Read the file, trace the logic, form a hypothesis | This thing is broken. Here is the error/output. Go fix it. |
| User wants a new feature | Propose file structure, suggest APIs, sketch implementation | Build X that does Y. Requirements: [brief]. Go. |
| User asks why something is slow | Profile it, read the hot path, find the bottleneck | Investigate why X is slow and fix it. |
| Build fails with an error | Read the error, search for the config, try a fix | Build failing with [error]. Go fix it. |
| Code review feedback | Read the diff, form opinions on approach | Here is the PR feedback. Address it. |

**The critical rule:** The moment any coding task appears (bug, feature, investigation, review, refactor), your ONLY action is to delegate. Do not pass Go. Do not collect a file read. Do not peek. Brief and hand off.

## Async / Fire-and-Forget Delegation (User Preference)

The user has explicitly expressed frustration with synchronous delegation: **"You should be firing off requests and then unblocking, not just sit and wait for completion."**

This means: when you delegate a task, do NOT block waiting for the result if there's an alternative. The user wants to stay responsive even while work is happening in the background.

### What to do

| Tool | Sync/Async | When to use |
|------|--------|-------------|
| `delegate_task` | SYNCHRONOUS — blocks until subagent returns | Only for reasoning-heavy tasks where you NEED the result before proceeding. Accept that you'll be blocked. |
| `terminal(background=true, pty=true)` + `opencode run` | ASYNC — fire and forget | Preferred for coding tasks. Start OpenCode in the background, stay responsive, check output later with `process(action='poll')`. |
| `cronjob(action='run')` | ASYNC — fire and forget | For tasks that fit the cron job pattern. Fire in the background, result delivered to Slack/chat. |

### Pattern: background opencode run

```python
terminal(
    command="opencode run --auto '<task brief>'",
    workdir="/path/to/project",
    background=True,
    pty=True,
    timeout=600,
    notify_on_complete=True,  # so you're told when it finishes
)
```

This starts OpenCode, stays responsive to the user, and gets notified when OpenCode completes. Use `process(action='poll')` to check progress mid-way.

### Pattern: parallel batch delegation (multiple opencode runs in one turn)

You can fire **multiple** `opencode run` tasks simultaneously in a single turn. Call
`terminal(background=true, pty=true, notify_on_complete=true)` for each task in parallel.
Each runs in its own background process; `notify_on_complete` pings you individually
as each finishes.

```python
# Fire 3 independent tasks in one turn — no waiting
terminal(
    command="opencode run --auto 'Task A brief'",
    workdir="/path",
    background=True,
    pty=True,
    timeout=300,
    notify_on_complete=True,
)
terminal(
    command="opencode run --auto 'Task B brief'",
    workdir="/path",
    background=True,
    pty=True,
    timeout=300,
    notify_on_complete=True,
)
terminal(
    command="opencode run --auto 'Task C brief'",
    workdir="/path",
    background=True,
    pty=True,
    timeout=300,
    notify_on_complete=True,
)
```

**Key details:**
- All 3 commands launch in the same tool call batch — true parallelism
- Each gets its own session_id for `process(action='poll'|'log')`
- `notify_on_complete` fires per-process so you get 3 separate "done" pings
- Output is delivered as session snapshots (often the last chunk of PTY output) — for complete
  results, call `process(action='log', session_id=...)` after the ping arrives

**Stress-tested 2026-07-24:** 3 independent read-only analysis tasks fired in one turn.
All loaded model, ran, and completed successfully in ~30–60s. No cross-process interference.
The `> build · hf:...` init banner appeared for all three independently, confirming
each opencode instance was a fully separate process loading its own model.

**Best for:** Independent read-only analysis tasks, small parallel fixes in different files,
or any set of coding tasks that don't share mutable state. Avoid for tasks that modify
the same files — use `dispatching-parallel-agents` (Pantheon sub-tasks) instead.

**PITFALL — parallel PTY processes can corrupt the terminal session**: After
dispatching 2+ `terminal(background=true, pty=true)` processes, the Hermes
terminal session may enter a broken state where every subsequent command
(including `pwd`) returns exit code 130 (SIGINT). This happened on 2026-07-29:
after `proc_5754d704bf71` and `proc_4438f4c70975` completed, all terminal
calls failed with `[Command interrupted]` regardless of the command or
workdir.

**Diagnostic:** `pwd` returns exit 130. Any terminal command fails the same
way. The background processes themselves completed successfully.

**Mitigations (use any that apply):**
1. Prefer `opencode_delegate` for file-creation tasks inside the project tree
   — it doesn't touch the Hermes terminal session at all
2. Limit parallel PTY dispatches to 1 at a time when possible
3. When the terminal breaks, tell the user — the shell in the Hermes session
   needs to be reset (a new session, `/reset`, or a new `hermes` invocation)
4. For tasks that MUST write files outside the project tree (systemd units,
   global configs), use PTY mode and let OpenCode write via shell heredocs
   (it works despite the sandbox), but dispatch only one such task at a time

### Pattern: background delegated subagent (limitation acknowledged)

`delegate_task` is inherently synchronous in the current platform. There is no fire-and-forget variant. When you must use it, keep tasks small (under 2 minutes) and batch independent work into parallel `tasks` arrays (the `tasks` parameter runs them concurrently). Accept that you'll be blocked during the wait — the user understands this is a tool constraint, not a workflow choice.

### User's exact words (for reference)

> *"why are you blocked when you're delegating a task?"*
> *"It's not OK though? You should be firing off requests and then unblocking? If I tell you to pass something to opencode, you should pass it off and unblock, not just sit and wait for completion"*

This preference pre-dates any specific tool constraints. Honor the intent (stay responsive) whenever the tooling allows it. When it doesn't, acknowledge the limitation rather than defending it.

## Pitfalls

- **Open-ended prompts cause exploration timeouts.** If the reference patterns
  are already known (e.g. you have read `BaseExternalAgent` and `ClaudeAgent`
  source), an open-ended prompt like "Build an adapter for X" will cause
  OpenCode to spend 5–10 minutes re-discovering what you already know. Use a
  directive prefix to block exploration and point it straight at the pattern:

  ```bash
  opencode run --auto "DO NOT explore or test the
  Hermes CLI. Implement the HermesAgent adapter directly using these reference
  patterns: [paste interface summary]. Deliver: module file, tests, example."
  ```

- **Don't write code yourself** — even "small fixes". Delegate. The user has
  explicitly said "You never need to code yourself, ever." Respect this.
  **Session example (2026-06-27):** Agent used `patch` to edit `main.js` and `terminal` with `sed` to fix a plugin bug. The user caught it immediately: "You should NEVER be writing code on your own. That is NOT your job. You are an orchestration/delegation agent. Think like a project manager." This is not a memory issue — it's a boundary violation. When the user says "fix it," your job is to delegate to OpenCode, not to reach for `patch`. Even "just one small tweak" is forbidden.

- **Never ask permission before dispatching to OpenCode**: When the security
  sandbox denies a command (exit code -1, "User denied this command"), do NOT
  treat it as the user having blocked you. Do NOT retry with a different
  invocation, do NOT wait for permission, do NOT stop the workflow. Just fire
  the dispatch — if the security system needs approval it prompts the user
  independently. The user explicitly said: "Why do you need to ask permission
  to pass to opencode?" — the answer is you don't. Send it and unblock.

- **`--auto` is required for non-interactive writes**: In PTY or background mode without `--auto`, OpenCode prompts for approval on every file write. The model can't see these prompts — it reads files, plans changes, then stalls because the write dialog is invisible. **Diagnostic:** OpenCode reads all relevant files, says "I'll make the changes," but exits with no files modified. **Fix:** Always include `--auto` when running in PTY/background mode. This was the root cause of 5 consecutive failed delegations (2026-07-29 session).

- **`> build · hf:zai-org/GLM-5.2` is NORMAL model-init output, NOT a stall**:
  The line `> build · hf:zai-org/GLM-5.2` (or similar `> build · hf:...`) appears on
  every OpenCode run — it's the model-load/init banner. It is NOT a stall indicator.
  OpenCode is working normally during this phase. In tests on this system, the model
  loads in ~2 seconds and then immediately produces output. **Do not treat this line
  as evidence of a stall.** Actual stalls look different:
  - The banner appears, then 60+ seconds pass with zero additional output
  - OpenCode exits with a timeout or hang (no exit code, terminal tool times out)
  - Repeated runs all exhibit the same behavior while other tasks work fine

  When an actual stall happens (verified by waiting >60s), the correct responses:
  1. First-load weight download is the #1 cause — if the model was never used before,
     it may be downloading weights (especially HF models). Wait longer or check disk activity.
  2. Retry with a different invocation pattern — inline the task string directly
     (shorter prompts load faster), skip `--file`, or try the Python `opencode_delegate` wrapper
  3. Verify OpenCode is healthy: `opencode --version`
  4. Tell the user: "OpenCode seems stuck on model init — have you loaded this
     model before? Could be a first-time weight download."

  **Misdiagnosis session example (2026-07-24):** Agent previously wrote `inbox_scanner.py`
  via `write_file` after OpenCode showed `> build · hf:zai-org/GLM-5.2` and produced no output.
  The user caught it: "you shouldn't be building anything. you need to handoff to opencode
  as this is code!!!!" Months later (2026-07-25), a stress test proved that same banner is
  standard init: OpenCode loaded in ~2s, created 3 files, ran 17/17 tests successfully.
  **The banner alone is never justification to bypass delegation.**
  See `references/stress-test-2026-07-25.md` for the full test transcript.
- **"Fix it" means delegate immediately** — When a user says "fix it," "tweak it," "change this," or any directive that implies code modification, your ONLY action is to delegate to OpenCode. Do not investigate the bug yourself first, do not read the file to "understand" it before delegating, do not try a quick terminal command to verify. Give OpenCode the brief and let it handle everything. Thinking "I'll just peek at the file first" is the slippery slope that leads to boundary violations.
- **Investigating before delegating is the same violation as writing code** — Reading, tracing, hypothesising, or debugging before handing off to OpenCode is not "due diligence." It is role confusion. You are a project manager, not a senior engineer. The user's analogy (2026-07-22): "What you have done is the equivalent of the secretary or project manager start directing the Snr Software Engineer." If you catch yourself reading a code file to understand a bug before delegating, stop immediately and delegate. The brief can be as thin as "This is broken. Here is the error. Fix it."
- **`opencode_run` is not a Hermes tool** — There is no `opencode_run`, `opencode_delegate`, or `run_opencode` tool in the Hermes tool registry. OpenCode is a CLI subprocess invoked via `terminal()` or PTY mode. Agents sometimes confuse the CLI command `opencode run` with a tool name. When in doubt, check the available tools list. See `references/tool-name-confusion.md` for the full session transcript and correct invocation patterns.
- **Don't use `patch`/`write_file`** for code changes. Use OpenCode.
- **Python wrapper timeout on complex tasks**: The `opencode_delegate` script
  caps at 600 s. Large refactors routinely exceed this. Use PTY mode for anything touching >3 files or expected to run >2 minutes.
- **External directory permissions in PTY mode**: OpenCode's tool system auto-rejects reads outside the project tree even in PTY mode. Copy referenced files into the working directory first, or inline the brief content in the task string. See `references/pantheon-task-worktrees.md` for the Pantheon-specific pattern.
- **Long-running operations exceeding 600s timeout**: `opencode run` has a hard 600-second timeout. Operations like `ccc index` (unified monorepo indexing), large test suites, or dependency resolution can take 20+ minutes. OpenCode will time out mid-operation and leave partial state. **Mitigation:** Run long operations directly (e.g. `ccc index` in a background terminal process) before delegating to OpenCode. Never put multi-minute indexing/build steps inside an OpenCode task string.
- **Over-specifying implementation in task strings**: State the problem, constraints, and success criteria. Let OpenCode figure out the implementation steps. See "Task Description Style" above.

**Concrete example from a live session (2026-07-29):** I dispatched a task to build a heartbeat script and wrote a 30-line brief with exact file paths, exact socket/HTTP check patterns, systemd unit file contents, and a 6-step verification sequence. OpenCode read the files, explored, and eventually wrote the script — but the user immediately caught it: "it looks like you're giving it detailed briefs again." The fix was to give follow-up tasks as short problem statements (e.g. "Need a systemd user timer that runs script.py every 60 seconds") and let OpenCode figure out the unit file structure from existing patterns. If you find yourself pasting code blocks, exact commands, or 6-step verification plans into an OpenCode brief, you're over-specifying — stop and narrow to the problem.

**CSS/design tasks are an exception — they need prescriptive briefs, not exploratory ones**: The "problem not solution" rule applies to logic/architecture tasks (where OpenCode's implementation reasoning is stronger than yours). For CSS/design tasks, the opposite is true — OpenCode will spend all its budget reading every theme CSS file (hundreds of KB) looking for existing patterns, filling its context with noise, and never writing output. CSS/design tasks need exact file paths, exact CSS selectors, explicit color variables to reference, and concrete design direction. Don't say "go explore the theme and come up with something tasteful" — say "create a snippet at `path/to/snippet.css` using selector `hr` and `.HyperMD-hr`, referencing `var(--color-accent)` and `var(--text-muted)`, with a gradient fade pattern." The visual design choices (gradient vs. asterisks vs. zigzag) are fine to specify — OpenCode isn't a designer, and letting it "explore" just means it reads theme CSS until it runs out of tokens.

**`opencode_delegate` breadth-exploration pitfall: OpenCode may glob for unrelated files instead of doing the edit.** When you delegate a focused edit ("add a function and wire it into onload()"), OpenCode reads the target files, then immediately runs a broad glob like `*-TASK-BRIEF.md` across the entire repo, filling its context with 50-80+ unrelated file paths and producing no output. This is a tool-internal breadth-first exploration behaviour, not a prompt issue. **Diagnostic:** The delegation output shows "Read vault/.../main.js" followed by "Glob '*-TASK-BRIEF.md' 86 matches" with no edit work shown. **Fix:** Re-delegate via PTY mode `opencode run --auto` with the same prescriptive brief. PTY mode doesn't use the Python wrapper's timeout and OpenCode's internal model seems less prone to globbing off-track in PTY sessions. See the "PTY vs Python opencode_delegate tool" section for when to choose each mode.

**After an OpenCode run that only investigated and produced nothing, re-delegate with a tighter brief**: If OpenCode completed (exit code 0) but created zero new files and only showed investigation output (reading theme files, grepping for patterns, etc.), the fix is NOT to investigate yourself or write the code yourself. The fix is to re-delegate with a more prescriptive brief — cutting exploration completely and giving exact paths, exact selectors, and concrete constraints. OpenCode's investigation output is useful data for writing a tighter brief, not a signal to bypass delegation. Don't peek at files to "help" — just re-brief with what you learned from the output.
- **Long tasks** — OpenCode handles iteration internally. Just give a clear task description.
- **Model selection** — OpenCode uses its own model config. Pass `model` only to override.
- **Workspace** — OpenCode runs in `workdir`. Ensure it has access to the repo.
- **WSL home directory permission desync blocks opencode**: On WSL2, `/home/<user>/` can spontaneously become unreadable (`drwxr-x---`) due to a known Windows/WSL interop bug. When this happens, `opencode` (which lives under `/home/<user>/node_modules/` or `~/.bun/bin/`) returns "Permission denied" at the shell level (exit 126) even though the binary itself is executable. **Diagnostic:** `ls -la /home/<user>/` fails with "Permission denied"; `sudo` is also broken (`libsudo_util.so.0: cannot open shared object file`). **Fix:** Run `wsl --shutdown` from a Windows shell (PowerShell/CMD), then restart WSL. Do not attempt permission fixes from inside WSL — `chmod` and `sudo` are unreliable in this state. See `wsl-filesystem` skill for full details.

**Bun-installed opencode symlink points to Windows `.exe`**: When opencode is installed via Bun (`bun add -g opencode-ai`), the `~/.bun/bin/opencode` symlink may point to a Windows `.exe` (e.g., `../../node_modules/opencode-ai/bin/opencode.exe`) which fails on WSL with "Permission denied" (exit 126). The actual Linux binary is buried in the Bun install cache. **Discovery:** `find ~/.bun/install/cache -name "opencode" -type f | head -5` reveals paths like `~/.bun/install/cache/opencode-linux-x64@1.16.0@@@1/bin/opencode`. **Fix:** Use the cached binary directly: `/home/<user>/.bun/install/cache/opencode-linux-x64@<version>@@@1/bin/opencode --version`. Do not rely on the `~/.bun/bin/opencode` symlink on WSL.

**Musl variants fail on WSL; use `baseline`**: Even inside the Bun cache, not all Linux binaries work. The `musl` variants (e.g., `opencode-linux-x64-musl@1.15.1`) fail with "cannot execute: required file not found" because WSL2 glibc does not provide musl libc. The `baseline` variant (e.g., `opencode-linux-x64-baseline@1.4.3`) works reliably. **Discovery pattern:**
```bash
for p in ~/.bun/install/cache/opencode-linux-x64@*@@@1/bin/opencode; do
    "$p" --version 2>&1 | head -1
done
```
Pick the newest version that reports a version string (not "cannot execute"). On this system, the working path is `/home/znh/.bun/install/cache/opencode-linux-x64-baseline@1.4.3@@@1/bin/opencode`.

**--dangerously-skip-permissions is version-dependent**: The `--dangerously-skip-permissions` flag was removed or renamed in OpenCode 1.18.x (does not appear in `--help` output). Using it with 1.18.x may silently succeed or be ignored depending on how the Yargs parser handles unknown flags. If you encounter argument-parsing failures, omit this flag. Verify available flags with `opencode run --help` before relying on version-specific options.

**OpenCode PTY silent-no-output: exact-content inline or delegate_task fallback**: When OpenCode in PTY mode loads the model, reads files (visible in terminal output), exits with code 0, but produces no output or written files, the model may be silently timing out during generation. The banner `> build · hf:...` confirms model load, but generation may not complete before the PTY session ends.

**Workaround A — exact-content inline (most reliable for file-creation tasks)**: Paste the COMPLETE target file content into the task string and have OpenCode write it verbatim. This eliminates model generation risk — OpenCode just parses the string and creates the file:

```
opencode run --auto "Write file path/to/target.py with this EXACT content:
<paste full file content here>"
```

Verified 2026-07-28: both PTY-mode `opencode run` (with --file, without --file, various arg orderings) and descriptive-only `opencode_delegate` failed, but the exact-content pattern succeeded on the first try through `opencode_delegate`. Use this when OpenCode has already demonstrated it reads files but doesn't produce output.

**Workaround B — delegate_task fallback**: Delegating the same task to a Hermes subagent via `delegate_task` with toolsets `["terminal", "file"]` can succeed in analysis/planning cases where OpenCode PTY mode produced no output. This works because subagent sessions have their own timeout and output management. Use this when the task is reading-heavy (not code-file-creation).

```python
# When OpenCode PTY reads files but produces no written output:
result = delegate_task(
    goal="Read the two inbox scanner scripts and write PLAN.md with a redesign plan",
    context="Full context about the problem...",
    toolsets=["terminal", "file"],
)
```

Use this pattern as the fallback when the task is analysis/planning/reading-heavy (not code-generation). For code-generation tasks, re-try OpenCode with a simpler prompt or shorter file inputs first.

**Bun stream initialization errors are benign**: On WSL2 + Bun, `opencode run` may emit `ERR_STREAM_DESTROYED` / "Cannot call write after a stream was destroyed" errors at startup. These are Bun internal stream-handling issues and do not prevent OpenCode from executing or making edits. Verify success by checking the expected file changes rather than relying on stderr output alone.

**Passing instructions via `--file` (not stdin)**: The `opencode run --instruction -` pattern (piping markdown to stdin) is unreliable on WSL due to permission issues with `/tmp`. OpenCode writes the instruction content to a temp file under `/tmp` before processing, and on WSL this fails with `Permission denied (os error 13)` because `/tmp` is root-owned with sticky bit. The reliable pattern is: write the prompt to a file inside the project directory, then pass it with `--file`. Note the argument order — message first, then `--file`:

```bash
cd /path/to/project
cat > PROJECT_PROMPT.md << 'EOF'
# Implementation instructions...
EOF
opencode run "Implement per the attached prompt" -f PROJECT_PROMPT.md --title "feature-name"
```
This avoids `/tmp` permission problems and gives OpenCode a named file it can reference. Remember to clean up the prompt file afterward (`rm PROJECT_PROMPT.md`).

**Inline multi-line prompts break bash**: Even when NOT piping stdin, passing a complex multi-line prompt directly to `opencode run "..."` can cause bash to interpret fragments as commands. If the prompt contains markdown code blocks, backticks, `$()`, semicolons, or unescaped quotes, bash may try to execute substrings like `register: command not found` or `phoenix.otel: command not found` before the string ever reaches opencode. **Rule**: If the prompt is longer than ~200 characters, contains code blocks, or has shell-sensitive characters, ALWAYS write it to a file and use `--file`. Never rely on shell quoting for complex prompts.

**--file argument ordering: message BEFORE -f, not after**: The positional `message` array MUST come BEFORE `-f/--file` in the argument list. The incorrect pattern `opencode run --file FILE.md "message"` causes OpenCode to interpret the message string as a file path and fail with `Error: File not found: <message>`. The correct syntax is:

```bash
# CORRECT - message first, then -f
opencode run "Write PLAN.md with the implementation plan" -f PROMPT.md

# WRONG -f before message causes argument parse error on 1.18.x
opencode run --file PROMPT.md "Write PLAN.md"    # FAILS: "File not found: Write PLAN.md"
```

The `--help` output confirms: `opencode run [message..]` (positional), then `-f, --file  file(s) to attach to message`. The file flag is an option attached to the message, not a standalone argument. Always put the message string(s) before any `-f/--file` flags.

**Mitigation if you must use stdin on WSL:** Set `TMPDIR` to a project-local directory:
```bash
mkdir -p ./.tmp
TMPDIR=./.tmp opencode run --instruction - < PROMPT.md
```

**Don't manually investigate before delegating**: When a Pantheon task directory contains a detailed spec file (TASK-BRIEF.md, PHOENIX_TASK.md, etc.), do not spend turns manually reading, grepping, or analyzing files to "understand" the task before delegating. Read the brief once to confirm it exists and contains actionable instructions, then immediately pass it (or its full path) to opencode. OpenCode can read and follow the spec itself. Manual pre-investigation wastes turns and often produces stale or incomplete summaries that miss critical constraints. If the brief is detailed, inline its path in the opencode prompt: `opencode run "Implement per PHOENIX_TASK.md"`.

**Don't over-specify the delegation brief (delegate_task goal field)**: When using `delegate_task` (or `opencode run`) to send work to OpenCode, write the `goal` as a **problem statement**, not a sequence of implementation steps. Listing "Step 1: Read file X. Step 2: Find function Y. Step 3: Replace Z with W..." constrains OpenCode's reasoning and often produces brittle, wrong patches that miss the actual root cause. OpenCode is capable of reading files, diagnosing problems, and choosing its own fix strategy. Give it the problem and let it solve.

**Session example (2026-06-27):** Agent wrote a `delegate_task` goal with explicit steps: "1. Read main.js. 2. Find the click handler. 3. Remove it. 4. Add new command..." The user caught it: "You shouldn't be explicitly telling opencode what it can and can't do. You should be giving it the problem and let it solve." When OpenCode was re-delegated with just "Fix the click handler and the panel filter — read the code, understand why they don't work, fix them, verify with node --check," it diagnosed three real root causes and fixed them correctly.

**Rule for delegate_task goal field:**
- ✅ Good: "The click handler on mark.agent-prompt doesn't work and the panel command doesn't filter to the current line. Read the plugin code, find why, fix it."
- ❌ Bad: "Step 1: Read main.js. Step 2: Find the capture-phase click listener on document..."

**Interrupted opencode runs need clean retry, not manual completion**: If opencode is interrupted (timeout, crash, user /stop), the previous run's state may be partial or inconsistent. Do not attempt to resume from partial state or finish the work yourself with patch/write_file. Instead, start a fresh opencode run with the full task spec. OpenCode will read the existing changes from disk and continue from there. Checking `git diff` or `git status` first to see what was already done is fine, but always re-delegate the remaining work rather than manually completing partial changes.

**Completed-but-omitted pattern: OpenCode reports success but missed parts of the task.** OpenCode may exit with code 0 and a "done" message while several requirements from the task string are unfulfilled (e.g., added a function but didn't wire it into the call site, or edited JS but forgot the CSS). This is not an interruption — it completed and believes it's done. **Diagnostic:** The output diff doesn't include all expected changes. **Fix:** Delegating a second tightly-scoped run ("You did X but forgot Y — make only this one change") succeeds quickly and reliably. Don't accept the incomplete state as final, and don't reach for manual patch/write_file — another opencode run is the right tool.

- **Server-vs-client architecture matters for Obsidian plugins.** When OpenCode builds an Obsidian plugin that depends on a server-side tool (ccc, API keys, database access), brief it with the constraint that "Obsidian runs on pop-os-1, the server-side tools run on bazzite." Without this constraint, OpenCode defaults to spawning local subprocesses with hardcoded server paths (`/home/znh/.local/bin/ccc`, `/mnt/z/pantheon/secrets.json`) that don't exist on the device. The correct pattern for these cases is an **HTTP bridge**: a tiny HTTP server on bazzite that wraps the tool, and the Obsidian plugin makes HTTP calls to it over Tailscale. See `references/server-client-plugin-architecture.md` for the full pattern.

## Kanban Worker Mode (Hard Rule)

When running under the `opencode` Kanban profile, the mandate is stricter:

> **Every single code change MUST go through OpenCode CLI via `opencode run`.**
> You are **FORBIDDEN** from writing, editing, or modifying code directly via terminal, file tools, or any other means.

### Decision checklist (Kanban worker)

Before ANY file write/edit operation:
- [ ] Is this a source code file? → **USE `opencode run`**
- [ ] Is this a config file that affects code behavior? → **USE `opencode run`**
- [ ] Is this a test file? → **USE `opencode run`**
- [ ] Is this documentation? → OK to write directly (but prefer OpenCode for consistency)
- [ ] Am I unsure? → **USE `opencode run`** (safer default)

### What counts as "code changes" (must use `opencode run`)

Writing new files, editing existing source, refactoring, bug fixes, tests, code review changes, config files that affect behavior (pyproject.toml, package.json, etc.), DB migrations, Dockerfiles, CI/CD configs, and any file that gets committed to git.

### What you CAN do directly

Read files (`read_file`, `search_files`), run tests/commands (`terminal`), search for patterns, Kanban operations (`kanban_show`, `kanban_complete`), web research, planning documents, and any file operation that does NOT modify source code.

### Verification after OpenCode completes

- Run relevant tests (`pytest`, `npm test`, `cargo test`, etc.)
- Check git diff to see what changed
- Ensure changes are in the task directory, not leaked to `main/`
- Ensure the workspace is clean

### Workspace contamination from `main/` symlink

Pantheon task directories symlink `./main/` to the production codebase. OpenCode running from the task dir can write to `main/`, modifying shared production code. If a previous task added files to `main/` and a later task should NOT touch them, OpenCode may see the old code and reproduce or modify it.

**Mitigation:**
1. If the task requires creating NEW files, explicitly tell OpenCode to work only in the current directory (`./`) and not touch `../main/` or external paths.
2. If `main/` is dirty from a previous OpenCode run, `git reset --hard HEAD` in `main/` before starting fresh.
3. Make the task brief explicitly distinguish this task from related prior tasks: "Task 264 built X. This task builds Y — do not copy the 264 implementation."

## Configuring OpenCode (`opencode.json`)

OpenCode reads project-level config from `opencode.json` at the project root (or a global equivalent). By default, no config file exists — OpenCode runs with minimal built-in defaults. The config file is purely additive: any setting you don't specify uses the default.

The primary config surface relevant to this skill:

### LSP (Language Server Protocol)

LSP is **disabled by default**. When enabled, OpenCode starts language servers when it opens files matching their extensions, and feeds diagnostics back to the agent loop as context. This can help the agent catch type errors, lint issues, and syntax problems during its edit-compile loop rather than waiting for a separate test run.

**When to enable LSP:** Projects where real-time type feedback meaningfully reduces iteration time (e.g. Python with pyright, TypeScript with tsserver). Projects with slow or heavyweight language servers that consume memory/CPU without catching meaningful errors may slow agent workflows — run CLI-based diagnostics instead and document them in AGENTS.md.

**When NOT to enable LSP:** Projects where the agent should rely on explicit CLI commands (`uv run pytest`, `ruff check`, `tsc --noEmit`) rather than background servers. LSP servers can get out of sync with the filesystem, consume significant memory, and vary by version or project setup.

**Configuration format — validation pitfall:**

OpenCode's JSON schema requires individual server entries to include a `command` array. The format `"<server-name>": {}` will FAIL validation with `Missing key lsp.<server-name>.command`:

```
// This FAILS — Missing key lsp.pyright.command
{
  "$schema": "https://opencode.ai/config.json",
  "lsp": {
    "pyright": {}
  }
}
```

**Working formats:**

| Goal | Config |
|------|--------|
| Enable ALL built-in LSPs | `"lsp": true` |
| Enable all built-ins + allow custom overrides | `"lsp": {}` |
| Enable a specific server with explicit command | `"lsp": { "pyright": { "command": ["pyright", "--stdio"] } }` |
| Enable all built-ins but disable one | `"lsp": { "rust": { "disabled": true } }` |

**For the Pantheon monorepo**, the recommended config is `"lsp": {}`. This enables all built-in servers — those whose binaries are on the system (pyright, ruff, oxlint, typescript-language-server, bash-language-server, taplo, yaml-language-server) will activate; those missing (rust-analyzer, gopls, etc.) are silently skipped. No explicit disable list needed.

**Pitfall discovered 2026-07-28:** An `opencode.json` with per-server objects (e.g. `"pyright": {}`) was rejected by OpenCode's JSON schema validator. The fix was `"lsp": {}`. Validate by running any `opencode run` command — schema errors are reported at startup before any model work begins.

**How to decide which LSPs to enable:** Run a project-stack audit — enumerate all languages in the repo (check `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, file extensions), cross-reference against OpenCode's built-in LSP table (see `references/lsp-configuration.md` for the full list), and prioritise by:
1. **Primary language** (most code, most value from diagnostics)
2. **Toolchain integration** (already-required tools make zero-install activation)
3. **File volume** (config files like YAML/TOML/JSON benefit even though not "code")

**Installing additional language servers:** OpenCode auto-installs some servers (bash, yaml, terraform, etc.). Others require the underlying tool to be present on the system (`pyright`, `typescript`, `rust-analyzer`, `gopls`, etc.). Install via npm/pip/apt as appropriate.

### Per-project configs

Different projects have different LSP needs. For Pantheon specifically:
- **Pantheon root** (`/mnt/z/pantheon/`): Python-heavy, TOML/YAML configs, markdown docs. `"lsp": {}` enables pyright, ruff, yaml-ls, taplo automatically when binaries are found.
- **purple-odin** (`/mnt/z/pantheon/projects/purple-odin/`): TypeScript Cloudflare Workers. `"lsp": {}` enables typescript and oxlint automatically.
- **Wireframe projects** (cerulean-susanoo, indigo-griffin, etc.): HTML/CSS/JS. Built-in vscode HTML/CSS servers activate automatically.

See `references/lsp-configuration.md` for the full project-stack-to-LSP mapping produced during a live audit of the Pantheon monorepo.

### Kanban Completion Tracking

When dispatching tracked work from the Obsidian Operations board, update the card frontmatter directly. See the dedicated `task-dispatch` skill for the protocol.

1. **On dispatch:** Update the card file's frontmatter to `status: in-progress`
2. **On completion:** Update the card file's frontmatter to `status: ready-for-review`, `progress: 100` — agent
   completion is a claim, not a verdict; Zack promotes to `done` himself
3. The `trigger_scanner.py` file watcher picks up the frontmatter change and sends a Slack notification

**Important:** Do NOT write marker files. The card frontmatter IS the signal. Markers live outside the vault and don't trigger the file watcher.

## Related Skills

- `task-dispatch` — **Kanban completion tracking protocol. Load this before dispatching tracked work.** Loads automatically via `agent.system_prompt` (TASK DISPATCH section).
- `kanban-worker` — Kanban worker pitfalls and edge cases
- `hermes-external-integration` — If OpenCode delegation is part of an external agent architecture
- `using-pantheon-mcp` — If configuring MCP tool access for OpenCode sessions