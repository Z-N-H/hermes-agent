# PRD-Style Brief Examples

Template for briefing OpenCode on any code task. Write the brief in your own words following this structure, then pass it to `opencode run` or `delegate_task`. Let OpenCode investigate, plan, and implement — do not dictate steps.

## Template

```
**Context:**
What exists, relevant architecture, files to read (briefly — let OpenCode find them).

**Issue:**
The problem to solve. What's broken, missing, or suboptimal.

**Intended behaviour:**
How it should work after the change. Concrete but implementation-agnostic.

**Acceptance criteria:**
Verifiable conditions that define done. What passing looks like.
```

## Real-World Example: Marker-System Removal

This is the brief from the 2026-07-29 session:

```
Simplify the completion-tracking architecture by removing the marker system.
The card frontmatter should be the single source of truth for task state.

Context: I've already deleted vault_completion_watcher.py and the
task-completions directory. What remains is to fix whatever else references
or depends on them.

Issue: The vault_completion_watcher and .pending/.done marker files add a
second state store alongside the Kanban card frontmatter. This causes sync
failures — the watcher only processes markers when a Kanban card changes,
so pure-marker completions sit unprocessed.

Intended behaviour: When a task completes, the card frontmatter is updated
directly (status: done, progress: 100). The trigger_scanner file watcher
picks up the card file change and sends a Slack notification. No markers,
no vault_completion_watcher.

Acceptance criteria:
- trigger_scanner.py no longer imports or calls vault_completion_watcher
- vault_kanban_dispatch.py sends a Slack DM when a card reaches status 'done'
- The task-dispatch skill references direct frontmatter updates, not markers
- The system prompt no longer mentions .pending, .done, or task-completions
- No remaining files or imports reference vault_completion_watcher
```

## Do NOT Do This

```
Step 1: rm vault_completion_watcher.py
Step 2: Edit line 49 of trigger_scanner.py to remove the import
Step 3: Edit line 702 to remove the scan call
Step 4: Add this function to vault_kanban_dispatch.py:
  def _notify_slack(...):
    ...
```

Over-specified. OpenCode reads the codebase — let it.
