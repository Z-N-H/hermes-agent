# --file Flag Argument Ordering

## Discovered: 2026-07-25 (OpenCode 1.18.4 baseline, Hermes)

## The Problem

Calling `opencode run --file FILE.md "message"` throws:
```
Error: File not found: Read the attached INBOX_PLAN_PROMPT.md file and write PLAN.md with a practical implementation plan
```

OpenCode's argument parser treats everything after `--file FILE.md` as another positional argument, not as the message.

## Correct Syntax

The positional `message` array MUST come before `-f/--file`:

```bash
# ✅ Works on 1.18.x
opencode run "Write PLAN.md" -f PROMPT.md

# Also works (multiple message strings, file flag last)
opencode run "Read" "the" "prompt" -f PROMPT.md
```

The `--help` output confirms the grammar:
```
opencode run [message..]

Positionals:
  message  message to send                                     [array] [default: []]

Options:
  -f, --file  file(s) to attach to message                       [array]
```

`[message..]` is positional, `--file` is an option on the message. Message first, file flag after.

## --dangerously-skip-permissions Is Absent in 1.18.x

Running `opencode run --help` on 1.18.4 baseline does NOT show `--dangerously-skip-permissions` as an option. The flag may have been removed or renamed. Do not rely on it with this version.

## PTY Silent-No-Output Pattern

Observed on 1.18.4 baseline:
1. `opencode run "..." -f PROMPT.md` starts correctly
2. Banner `> build · hf:...` appears (model loads)
3. File-reading messages appear (`→ Read script.py`)
4. Exit code 0, but no written files or terminal output beyond reads

**Workaround A — exact-content inline (most reliable for file-creation)**: Paste the complete target file content into the task string. Skips model generation — OpenCode just writes what you give it. See the opencode-worker SKILL.md pitfall for details.

**Workaround B — delegate_task fallback**: Use `delegate_task` with `toolsets=["terminal", "file"]` for planning/analysis tasks where OpenCode silently stops after reading files.
