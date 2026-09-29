# Tool Name Confusion: `opencode_run` is Not a Hermes Tool

## Session: 2026-06-28

## Mistake
Agent attempted to call `opencode_run` as a Hermes tool:

```python
opencode_run(command="...")
```

This tool does not exist in the Hermes toolset. The call failed with:
```
Tool 'opencode_run' does not exist. Available tools: browser_back, browser_click, ...
```

## Root Cause
Confusion between the CLI command `opencode run` and a hypothetical Hermes tool name `opencode_run`. OpenCode is a CLI tool invoked via `terminal`, not a native Hermes tool.

## Correct Invocations

**Update (2026-07-29): `opencode_delegate` now exists as a real Hermes tool.** On 2026-07-26 the `opencode_worker` plugin (`.hermes/plugins/opencode_worker/`) registered a proper JSON-schema'd `opencode_delegate` tool (`task`, `workdir`, `model`, `timeout` params), gated on `opencode` being on `PATH`. It's a synchronous wrapper (no PTY/background/notify support) — good for quick/self-contained tasks. There is still no `opencode_run` or `run_opencode` tool; that name confusion from the original session below is unchanged.

### 1. `opencode_delegate` tool — quick, synchronous, script-gen/simple fixes
```python
opencode_delegate(
    task="Fix the login bug in auth.py — JWT validation fails on expired tokens",
    workdir="/path/to/project",
)
```

### 2. PTY mode via terminal() — complex/multi-file tasks, needs background+notify
```python
terminal(
    command="opencode run --auto 'Implement feature per TASK-BRIEF.md'",
    workdir="/path/to/project",
    background=True,
    pty=True,
    notify_on_complete=True,
    timeout=600,
)
```
Note: the project directory goes in the `workdir` param only — never `cd <path> &&` inside the command string, and never appended as a trailing bare argument after the task message (`opencode run`'s message positional is an array; a trailing bare arg gets silently absorbed into it and garbles the prompt). `--dangerously-skip-permissions` was removed in OpenCode 1.18.x; use `--auto`.

### 3. File-based instructions (WSL-safe, for long/complex prompts)
```python
terminal(
    command='cat > PROJECT_PROMPT.md << \'EOF\'\n# Implementation instructions...\nEOF && opencode run --auto "Implement per the attached prompt" -f PROJECT_PROMPT.md --title "feature-name" && rm PROJECT_PROMPT.md',
    workdir="/path/to/project",
    timeout=600,
)
```
Note: message comes before `-f/--file`, not after — see `references/file-flag-ordering.md`.

## Key Takeaway
`opencode_delegate` is a real Hermes tool (see update above) for quick/synchronous delegation. For complex or long-running tasks, OpenCode is still invoked as a subprocess via `terminal()` with `pty=True`/`background=True`/`notify_on_complete=True`, using `workdir=` (never `cd &&` or a trailing positional) to set the project directory. There is no `opencode_run` or `run_opencode` tool. Check the available tools list before assuming a tool name exists.

## Secondary Boundary Violation in Same Session
After the tool call failed, the agent proceeded to use `patch` to edit `gemini_client.py` directly rather than delegating to OpenCode via `terminal`. This was a two-line config change (model version strings), but **any code modification — including config updates — must go through OpenCode**. The skill's existing "Don't write code yourself — even 'small fixes'" pitfall applies here. Agents may rationalize "it's just a quick find-and-replace" but that is exactly the slippery slope the boundary is designed to prevent.
