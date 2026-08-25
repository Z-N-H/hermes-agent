# File-Trigger Integration Reference

Session-specific detail for event-driven Hermes triggers from file-based external systems.

---

## Known-Good Architecture: Obsidian Vault + Hermes

A validated production pattern for embedding Hermes inside an Obsidian vault via `<mark class="agent-prompt" data-request="...">` tags.

### Components

| Component | Path | Role |
|-----------|------|------|
| `trigger_scanner.py` | `vault/ZNH/scripts/trigger_scanner.py` | `watchdog` event handler that debounces file changes, extracts agent-prompt tags, and queues pending triggers. |
| `process_trigger.py` | `vault/ZNH/scripts/process_trigger.py` | Instant background processor spawned per trigger. |
| Cron safety net | `68f06099b1f8` every 30m | Hermes cron job with full toolsets (`terminal`, `file`, `search`, `skills`, `vision`) that processes anything the instant processor missed. |
| Response sink | `vault/ZNH/agent-responses/` | Markdown files written by both instant and cron processors. |
| Status feedback | `data-status` attr on `<mark>` tags | CSS-driven visual states (`processing` → green, `completed` → checkmark). |

### Trigger Tag Format

```markdown
<mark class="agent-prompt" data-request="Carry out the task." data-trigger-id="c48d4988dd9b0081">Do the task above</mark>
```

- `data-request` — the actual prompt sent to Hermes.
- `data-trigger-id` — stable UUID for deduplication and response linking.
- `data-status` — optional; set by the scanner (`processing`) and processor (`completed`).
- The highlighted text between `<mark>` and `</mark>` becomes `highlighted_context`.

### Response File Format

Both instant and cron processors must write responses with this exact frontmatter:

```yaml
---
type: trigger-response
trigger_id: <uuid>
source_file: <relative/path/to/source.md>
status: completed
processed_at: <ISO-8601 timestamp>
---

# Trigger Response

## Original Instruction

> <the data-request text>

## Source

- File: `<source_file>` (block `<source_block>`)

## Response

<Hermes-generated content>
```

---

## Correct Implementation: Hermes CLI Subprocess

`process_trigger.py` must invoke Hermes via subprocess, not the LLM API directly. This is the only way to get full tool access, memory, and gateway integration.

```python
import subprocess
from pathlib import Path


def _resolve_hermes_path() -> str:
    """Find the Hermes CLI executable. Falls back to known locations when
    PATH is not inherited (e.g. spawned from systemd, Obsidian, or with
    start_new_session=True).
    """
    import shutil

    path = shutil.which("hermes")
    if path:
        return path
    fallbacks = [
        "/home/znh/.local/bin/hermes",
        "/mnt/z/pantheon/.hermes/hermes-agent/venv/bin/hermes",
    ]
    for p in fallbacks:
        if Path(p).exists():
            return p
    return "hermes"


def _call_hermes(prompt: str) -> str:
    """Call Hermes CLI as a one-shot query and capture the clean response."""
    import os

    # Use the wrapper script (sets HERMES_HOME) rather than the raw venv binary
    hermes_path = "/home/znh/.local/bin/hermes"
    cmd = [hermes_path, "chat", "-q", prompt, "--quiet", "--source", "tool"]

    # CRITICAL: pass HERMES_HOME explicitly so the spawned session loads the
    # correct profile, skills, memory, and toolsets. Without this, Hermes
    # runs bare-metal with zero config even if the binary is found.
    env = os.environ.copy()
    env["HERMES_HOME"] = "/mnt/z/pantheon/.hermes"

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
        stdin=subprocess.DEVNULL,
        env=env,
    )
    if result.returncode != 0 and result.stderr:
        print(f"Hermes stderr: {result.stderr.strip()}", file=sys.stderr)

    output = result.stdout.strip()
    # --quiet still emits "session_id: <uuid>" as the first line — strip it
    lines = output.splitlines()
    if lines and lines[0].startswith("session_id:"):
        output = "\n".join(lines[1:]).strip()
    return output
```

---

## Pitfall 1: Direct LLM API Call (No Tools)

### The Bug

Calling the LLM directly via `requests.post` to `/chat/completions`:

```python
# WRONG — produces plain text with zero tool access
resp = requests.post(
    "https://api.synthetic.new/openai/v1/chat/completions",
    headers={"Authorization": f"Bearer {api_key}"},
    json={"model": MODEL, "messages": messages, "temperature": 0.7},
    timeout=120,
)
```

### Symptoms

The model responds with honest disclaimers like:

> "I can't directly read files from your Obsidian vault..."
> "I don't have access to external tools like Slack..."

The model is correctly reporting its actual capabilities. The direct API call has no tool schemas, no dispatch loop, no memory, and no gateway context.

### Fix

Replace with `_call_hermes()` (see "Correct Implementation" above). `hermes chat -q` loads the default profile's toolsets, initializes memory, and runs the full tool-use loop.

---

## Pitfall 2: `start_new_session=True` Breaks PATH

### The Bug

When the scanner spawns the instant processor with `subprocess.Popen(..., start_new_session=True)`, the child process does not inherit the parent's `PATH`. The bare command `hermes` raises:

```
FileNotFoundError: [Errno 2] No such file or directory: 'hermes'
```

### Fix

Use `_resolve_hermes_path()` (see "Correct Implementation" above) which tries `shutil.which("hermes")` first, then falls back to known absolute paths.

---

## Pitfall 2b: `HERMES_HOME` Not Set → Bare Session with Zero Config

### The Bug

Even when `_resolve_hermes_path()` finds a valid Hermes binary, the spawned session may run with **no config, no skills, no memory, and no toolsets** if `HERMES_HOME` is not set in the subprocess environment.

The wrapper script at `/home/znh/.local/bin/hermes` contains:
```bash
export HERMES_HOME=/mnt/z/pantheon/.hermes
exec "/mnt/z/pantheon/.hermes/hermes-agent/venv/bin/hermes" "$@"
```

But if `_resolve_hermes_path()` falls back to the raw venv binary (`/mnt/z/pantheon/.hermes/hermes-agent/venv/bin/hermes`) because `shutil.which("hermes")` returned `None` (PATH not inherited), the wrapper is never executed and `HERMES_HOME` remains unset.

### Symptoms

- The model responds as if it has never met the user, even though memory/skills are configured.
- Simple questions like "what do you code with?" get generic answers instead of personalized ones.
- The spawned session lacks all tool access, skills, and user profile context.
- Running the same prompt directly in a terminal works correctly.

### Fix

Always set `HERMES_HOME` explicitly in the subprocess environment, and prefer the wrapper script over the raw venv binary:

```python
import os

hermes_path = "/home/znh/.local/bin/hermes"  # wrapper script, not venv binary
cmd = [hermes_path, "chat", "-q", prompt, "--quiet", "--source", "tool"]

env = os.environ.copy()
env["HERMES_HOME"] = "/mnt/z/pantheon/.hermes"

result = subprocess.run(cmd, ..., env=env)
```

Also pass `--source tool` so the session is tagged as a tool integration, which helps with session filtering and avoids polluting the user's interactive session history.

### Related

- This is distinct from Pitfall 6 (Context Loss in Fresh Sessions). Pitfall 6 is about conversation history not transferring; this is about **configuration not loading at all**.
- Both issues compound: without `HERMES_HOME`, the session has no config; without a context prepend, the session has no user knowledge. Fixing both is required for fully contextual responses.

---

## Pitfall 3: `--quiet` Still Emits `session_id:`

### The Bug

`hermes chat -q --quiet` suppresses the banner, spinner, and tool previews, but still prints the session ID on the first line:

```
session_id: 20260627_140600_d84b8d
Hermes CLI test passed
```

If this line is written into the response markdown, it leaks into the Obsidian note.

### Fix

Strip the `session_id:` line before returning:

```python
lines = output.splitlines()
if lines and lines[0].startswith("session_id:"):
    output = "\n".join(lines[1:]).strip()
```

---

## Pitfall 4: Hermes Hangs on `stdin` in Detached Sessions

### The Bug

When `process_trigger.py` is spawned with `subprocess.Popen(..., start_new_session=True)` (common for systemd services, file watchers, and background daemons), Hermes's `chat -q` command blocks waiting for input on `stdin` — even though the prompt is passed as a CLI argument. The subprocess appears to hang forever (until the 600-second timeout kills it), returning an empty or truncated response.

**Why:** `start_new_session=True` creates a new POSIX session. Hermes's prompt toolkit or input handling may still try to read from the controlling terminal or stdin pipe, and without a real terminal or EOF, it blocks.

### Symptoms

- Response file is written but contains only the frontmatter — the `## Response` section is empty.
- `process_trigger` log shows the Hermes subprocess timing out after 10 minutes.
- Running the same `hermes chat -q` command directly in a terminal works fine.

### Fix

Pass `stdin=subprocess.DEVNULL` to `subprocess.run`:

```python
result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
    timeout=600,
    check=False,
    stdin=subprocess.DEVNULL,  # Prevent Hermes from blocking on stdin
)
```

This explicitly closes stdin, signaling to Hermes that no interactive input is expected.

---

## Pitfall 5: Trigger ID Mismatch (Absolute vs Relative Path)

### The Bug

If the scanner computes `trigger_id` using the **absolute** filesystem path (e.g., `/mnt/z/pantheon/vault/ZNH/Inbox/Note.md`) while the Obsidian plugin computes it using the **relative** vault path (e.g., `Inbox/Note.md`), the IDs will never match. The scanner sees a "new" trigger and queues it, but the log entry uses a different ID than the `data-trigger-id` already written in the markdown. The instant processor then fails with:

```
ERROR: Trigger <id> not found in log
```

### Fix

Ensure both the scanner and the plugin hash the same input. The plugin uses:

```javascript
// Obsidian plugin: computeTriggerId()
const text = `${sourceFile}:${instruction}:${highlightedContext}`;
// sourceFile is relative to vault root
```

So the scanner must match:

```python
# Python scanner: _get_mark_trigger_id()
def _get_mark_trigger_id(filepath: Path, inner_text: str, data_request: str) -> str:
    rel_path = str(filepath.relative_to(VAULT_PATH))
    content = f"{rel_path}:{data_request}:{inner_text}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]
```

The order matters: `{relative_path}:{data_request}:{inner_text}` must match the plugin's `{sourceFile}:{instruction}:{highlightedContext}`.

---

## Pitfall 6: Context Loss in Fresh Sessions

### The Bug

`hermes chat -q` always spawns a **brand-new Hermes session** with zero memory context, no conversation history, and no user profile. Even though tool access, file I/O, and web search work perfectly, the model responds as if it has never met the user:

> "I don't have any specific information about what you personally use to code..."

The model is not broken — it is correctly reporting that a fresh session has no memory of previous conversations or user preferences.

### Symptoms

- Simple factual questions get generic, impersonal answers.
- The model asks clarifying questions that should already be known ("what stack do you use?", "what is your preference?").
- Responses feel like they came from a public chatbot, not a personal assistant.
- The exact same prompt asked in an active Hermes session gives a rich, personalized answer, but the Obsidian trigger version does not.

### Fix

Prepend a system-style context block to every prompt before calling `hermes chat -q`. Store this as a constant or read it from a file so it stays in sync as preferences evolve.

```python
# In process_trigger.py → _build_prompt()
USER_CONTEXT = """You are assisting Zack NH (the user). Context you must respect:
- Zack is an orchestration agent, not an individual contributor (IC).
- ALL coding work is delegated to OpenCode; never solve code problems directly yourself.
- Plugin-first mindset, Pantheon MCP, reuse services rather than building from scratch.
- Branding preference: Nerd Font over emoji.
- UI preference: clean/minimal with Linear-quality sleekness.
- Agent triggers should be processed instantly/event-driven.
- Preserve current session context where possible.
Respond as the user's personal assistant, not a generic LLM."""


def _build_prompt(trigger: dict, source_text: str) -> str:
    parts = [USER_CONTEXT]
    parts.append(
        "You are processing a task from an Obsidian vault. "
        "Use your full toolkit to complete the request."
    )
    # ... rest of prompt assembly ...
    return "\n\n".join(parts)
```

**What to include in the context block:**
- User's role and workflow (orchestration vs IC, delegation patterns).
- Tool preferences (OpenCode for code, Pantheon MCP for integrations).
- Branding/UI conventions (Nerd Font, clean/minimal, Linear-quality).
- Architectural preferences (event-driven, plugin-first, reuse over rebuild).
- Any facts that would change how the assistant answers (tech stack, design system, deployment targets).

**What NOT to include:**
- Session-specific transient state (current task, temporary blockers).
- API keys or secrets (they belong in `.env`).
- Ever-changing data (use web search or file tools for live info).

### Why This Works

`hermes chat -q` does load the profile's toolsets, memory system, and skills — but it starts a **new SQLite session row** with an empty conversation history. The memory provider (e.g., Hindsight) may surface some long-term facts if configured, but short-term session context and user profile details from the *calling* session do not transfer. By embedding the essential user context directly in the prompt, the spawned session behaves like a continuation rather than a cold start.

### Related

- For true cross-session persistence (where the spawned session *inherits* the parent's session ID and history), use PTY mode with `--resume <session_id>` (see `hermes-agent` skill → "Spawning Additional Hermes Instances").
- For scheduled/cron triggers that also need context, use the same `USER_CONTEXT` constant so all entry points stay consistent.

---

## Evolution: Hindsight Memory Injection for Dynamic Context

### The Problem with Static Context

The static `USER_CONTEXT` block in Pitfall 6 works for fixed facts (role, workflow, branding), but it cannot adapt to the specific question being asked. When a trigger asks "what do you code with?", the static block may not contain enough detail about the user's actual toolchain. The model still guesses.

### The Solution: Query Hindsight Before Calling Hermes

If the Hermes profile uses Hindsight as its memory provider, `process_trigger.py` can query the local Hindsight API for memories relevant to the trigger content, then inject those memories into the prompt.

### Implementation

```python
import json
import urllib.request
from pathlib import Path


def _fetch_hindsight_memories(query: str, max_tokens: int = 1024) -> str:
    """Query the local_external Hindsight API for relevant user memories."""
    config_path = Path("/mnt/z/pantheon/.hermes/hindsight/config.json")
    if not config_path.exists():
        return ""
    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (json.JSONDecodeError, OSError):
        return ""

    mode = cfg.get("mode", "")
    api_url = cfg.get("api_url", "")
    if mode != "local_external" or not api_url:
        return ""

    bank_id = cfg.get("bank_id", "hermes")
    url = f"{api_url.rstrip('/')}/v1/default/banks/{bank_id}/memories/recall"
    payload = {
        "query": query,
        "types": ["world", "experience"],
        "budget": "mid",
        "max_tokens": max_tokens,
        "trace": False,
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return ""

    results = data.get("results", [])
    texts = [r.get("text", "") for r in results if r.get("text")]
    if not texts:
        return ""
    return "\n".join(f"- {t}" for t in texts)


def _build_prompt(trigger: dict, source_text: str) -> str:
    request = trigger.get("request", "")
    instruction = trigger.get("instruction", "")
    highlighted = trigger.get("highlighted_context", "")
    surrounding = trigger.get("surrounding_context", "")
    source_file = trigger.get("source_file", "")

    parts = []
    parts.append(USER_CONTEXT)  # static base context from Pitfall 6
    parts.append(
        "You are processing a task from an Obsidian vault. "
        "Use your full toolkit to complete the request."
    )

    # Dynamic: fetch relevant memories from Hindsight
    hindsight_query = (
        f"Zack NH {request or instruction or 'preferences tools coding setup projects'}"
    )
    hindsight_memories = _fetch_hindsight_memories(hindsight_query)
    if hindsight_memories:
        parts.append(f"Relevant memories about the user:\n{hindsight_memories}")

    if request:
        parts.append(f"Request: {request}")
    if instruction and not request:
        parts.append(f"Instruction: {instruction}")
    if highlighted:
        parts.append(f"Highlighted context:\n{highlighted}")
    if surrounding:
        parts.append(f"Surrounding context:\n{surrounding}")
    if source_text and not highlighted:
        parts.append(f"Full source text:\n{source_text}")
    if source_file:
        parts.append(f"Source file: {source_file}")

    return "\n\n".join(parts)
```

### Key Points

- **Timeout is short (3s)** — the trigger processor must not hang if the Hindsight daemon is offline. A failed query gracefully falls back to the static context block.
- **Query includes the user's name** — prepending "Zack NH" to the trigger content helps the memory system surface user-specific facts over generic ones.
- **`types: ["world", "experience"]`** — these are the most useful memory types for user preferences and factual knowledge. Adjust based on your hindsight configuration.
- **`budget: "mid"`** — balance between token cost and recall quality. Use `"low"` for cheaper, `"high"` for more thorough.
- **Graceful degradation** — if Hindsight returns nothing, the prompt still works with just the static context.

### When to Use

- **Always** if Hindsight is running in `local_external` mode and the trigger requests are user-facing (not pure automation).
- **Especially** for open-ended questions where the static context block might not contain the specific answer.
- **Skip** for fully deterministic automation (e.g., "run this specific script") where personal context adds no value.

### Why Not Just Rely on Hindsight Inside `hermes chat -q`?

`hermes chat -q` does load the profile's memory provider, but it starts a **fresh session** with an empty conversation. The memory system may auto-recall on the first turn, but the recall happens *after* the prompt is already being processed by the model. By injecting memories into the prompt itself, the model sees them during its first reasoning step, leading to more contextual initial responses.

---

## Feature: Visual Status Feedback via `data-status`

### What It Does

The `<mark class="agent-prompt">` tag gains a `data-status` attribute that drives CSS styling in Obsidian, giving instant visual feedback without Slack messages:

| State | Attribute | Visual |
|-------|-----------|--------|
| Queued | (none or default) | Accent-coloured pill with robot icon |
| Processing | `data-status="processing"` | Green robot icon + stronger border |
| Completed | `data-status="completed"` | Muted grey checkmark + 75% opacity |

### How It Works

**1. Scanner sets `processing` when a trigger is queued**

In `trigger_scanner.py` → `queue_trigger()`:

```python
if trigger.get("type") == "mark":
    _update_mark_status(source_path, trigger["id"], "processing")
```

**2. Processor sets `completed` when the response is written**

In `process_trigger.py` → after `_write_response()`:

```python
updated = _update_mark_status(source_path, trigger_id, "completed")
```

**3. `_update_mark_status()` helper (both files)**

```python
import re


def _update_mark_status(filepath: Path, trigger_id: str, status: str) -> bool:
    text = filepath.read_text(encoding="utf-8")
    trigger_id_escaped = re.escape(trigger_id)
    pattern = (
        rf'(<mark\b[^>]*\bdata-trigger-id=["\']{trigger_id_escaped}["\'][^>]*?)'
        rf'(\s+data-status=["\'][^"\']*["\'])?'
        rf"([^>]*)>"
    )

    def replace(m):
        prefix = m.group(1)
        rest = m.group(3)
        return f'{prefix} data-status="{status}"{rest}>'

    new_text, count = re.subn(pattern, replace, text, count=1)
    if count == 0:
        return False
    filepath.write_text(new_text, encoding="utf-8")
    return True
```

## CSS rules in `styles.css`**

Theme-compatible approach using HSL CSS variables (works across Minimal, Baseline, AnuPpuccin, and custom skins):

```css
/* Base: accent-coloured pill with robot icon */
mark.agent-prompt {
    display: inline-flex;
    align-items: center;
    vertical-align: middle;
    background: hsla(var(--accent-h), var(--accent-s), var(--accent-l), 0.12);
    background: color-mix(in srgb, var(--interactive-accent) 12%, transparent);
    border: 1px solid hsla(var(--accent-h), var(--accent-s), var(--accent-l), 0.40);
    border: 1px solid color-mix(in srgb, var(--interactive-accent) 40%, transparent);
    border-radius: 12px;
    padding: 1px 6px 1px 8px;
    transition: background-color 0.15s ease, border-color 0.15s ease;
}

mark.agent-prompt:hover {
    background: hsla(var(--accent-h), var(--accent-s), var(--accent-l), 0.20);
    background: color-mix(in srgb, var(--interactive-accent) 20%, transparent);
}

/* Robot icon pseudo-element */
mark.agent-prompt::after {
    content: "";
    display: inline-block;
    width: 1.35em;              /* scales with parent text size */
    height: 1.35em;
    margin-left: 0.45em;         /* proportional gap */
    flex-shrink: 0;
    border-radius: 0.35em;       /* slightly rounded, not a full circle */
    background-color: color-mix(in srgb, hsl(340, 70%, 65%) 60%, var(--interactive-accent) 40%);
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%23ffffff' stroke-width='2.25' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 8V4H8'/%3E%3Crect width='16' height='12' x='4' y='8' rx='2'/%3E%3Cpath d='M2 14h2'/%3E%3Cpath d='M20 14h2'/%3E%3Cpath d='M15 13v2'/%3E%3Cpath d='M9 13v2'/%3E%3C/svg%3E");
    background-size: 0.9em 0.9em;  /* SVG icon scales with the box */
    background-repeat: no-repeat;
    background-position: center;
    opacity: 1;
    filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.35));
    transition: background-color 0.2s ease, opacity 0.2s ease, filter 0.2s ease;
}

mark.agent-prompt:hover::after {
    background-color: color-mix(in srgb, hsl(340, 75%, 58%) 65%, var(--interactive-accent) 35%);
    filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.4));
}

/* Processing: theme-fitting green */
mark.agent-prompt[data-status="processing"] {
    border-color: color-mix(in srgb, var(--interactive-accent) 50%, transparent);
}
mark.agent-prompt[data-status="processing"]::after {
    background-color: color-mix(in srgb, hsl(140, 65%, 48%) 55%, var(--interactive-accent) 45%);
    filter: drop-shadow(0 1px 3px rgba(0, 0, 0, 0.45));
}

/* Completed: muted grey checkmark */
mark.agent-prompt[data-status="completed"] {
    opacity: 0.75;
}
mark.agent-prompt[data-status="completed"]::after {
    background-color: #9ca3af;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M20 6 9 17l-5-5'/%3E%3C/svg%3E");
    background-size: 0.65em 0.65em;
    opacity: 0.90;
}
```

**Key CSS variable facts for Obsidian themes:**
- `--interactive-accent-rgb` is **NOT** defined by many themes (Minimal, default). Always prefer `hsla(var(--accent-h), var(--accent-s), var(--accent-l), ...)` or `color-mix(in srgb, var(--interactive-accent) ...)` — these work across all themes.
- `--interactive-accent` and `--accent-h`/`--accent-s`/`--accent-l` are the safe, universal accent variables.

### Why This Matters

- **No Slack dependency** — the feedback is right there in the note.
- **Instant acknowledgement** — green icon appears within ~1 second of saving the file.
- **Completion signal** — grey checkmark tells the user the response is ready without switching panes.

---

## Decision: Instant Processor vs Cron Safety Net

| Concern | Instant (`process_trigger.py`) | Cron (`hermes cron run`) |
|---------|-------------------------------|--------------------------|
| Latency | ~1–5 seconds | Up to 30 minutes |
| Tool access | Full if using `hermes chat -q` | Full |
| Failure handling | Must catch and retry manually | Automatic retry on next tick |
| Queue depth | Spawns one process per trigger | Processes all pending in batch |
| Resource use | Higher (many short-lived processes) | Lower (single batch run) |
| Visual feedback | Yes (`data-status` updated live) | No (batch, no per-trigger UI) |

Recommended: keep **both**. The instant processor handles the "within seconds" expectation and live UI feedback; the cron catches anything that crashed, timed out, or was created while the scanner wasn't running.

---

## Related

- `hermes-external-integration` SKILL.md → Pattern 1c: Lightweight Trigger Integration
- `hermes-agent` skill → "Spawning Additional Hermes Instances" for PTY/multi-turn variants
