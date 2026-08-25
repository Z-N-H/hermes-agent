# Pantheon Task Worktree Structure

Pantheon tasks are implemented as **git worktrees**, not branches. Each task directory under `tasks/<task-id>/` is a worktree with `main/` symlinked in.

## Directory Layout

```
projects/purple-phoenix/
├── main/                          # Source of truth (main branch)
│   ├── agent_context/scripts/
│   ├── agent_context/tui/
│   ├── tests/
│   └── ...
│
└── tasks/266-unified-pantheon-semantic-search/   # Git worktree
    ├── .git                       # Points to main repo's .git
    ├── .task.json                 # Task metadata (status, assignee, PR)
    ├── TASK-BRIEF.md              # The task spec
    ├── README.md                  # Usually a copy of main's README
    ├── pyproject.toml             # Symlink or copy from main
    ├── uv.lock                    # Symlink or copy from main
    ├── PROJECT_KNOWLEDGE -> ../../main/docs
    ├── READ_ONLY_REFERENCE_CODE -> ../../main
    ├── agent_context/             # Copied from main; edits here get merged
    ├── tests/                     # Copied from main; new tests go here
    └── data/, docs/               # Task-specific artifacts
```

## Key Implications for OpenCode Delegation

1. **Work happens in the task worktree, not `main/` directly.** OpenCode should be launched from the task directory (`tasks/<id>/`).

2. **Edits to `agent_context/` in the worktree** are what get committed and merged to main via PR.

3. **Task briefs live in the worktree root** (`tasks/<id>/TASK-BRIEF.md`). If OpenCode needs to read the brief while working in `main/`, copy it first:
   ```bash
   cp tasks/266-unified-pantheon-semantic-search/TASK-BRIEF.md main/TASK-BRIEF-266.md
   cd main && opencode run "Read TASK-BRIEF-266.md and implement..."
   ```

4. **`.task.json` is the metadata source of truth.** It tracks status, assigned model, PR number, and progress. Do not manually edit without understanding the schema.

5. **Symlinks (`PROJECT_KNOWLEDGE`, `READ_ONLY_REFERENCE_CODE`)** point to `main/docs` and `main/` respectively. OpenCode can follow these for reference but should not edit through them — edits must happen in the worktree's own `agent_context/` copy.

## Common Pitfalls

- **Launching OpenCode from `main/` instead of the task worktree** → changes go to main branch directly, bypassing the task/PR workflow.
- **Referencing `../tasks/<id>/TASK-BRIEF.md` from `main/`** → OpenCode's tool system auto-rejects external-directory reads. Copy the brief into `main/` first.
- **Assuming task 264 and task 266 code are independent** → task worktrees copy `main/` at creation time. If task 264 was merged to main after task 266's worktree was created, the 266 worktree won't have those changes unless rebased.
