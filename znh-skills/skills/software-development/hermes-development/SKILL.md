---
name: hermes-development
description: "Extend and develop Hermes: skill authoring, skin customization, and provider fast-mode extensions."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, development, skills, authoring, skin, fast-mode, provider, extension]
    related_skills: [hermes-agent, hermes-external-integration]
---

# Hermes Development

Extend and customize Hermes Agent: author in-repo skills, build terminal skins, and add provider-aware fast-mode overrides.

---

## Skill Authoring (In-Repo)

Skills live in two places:
1. **User-local:** `~/.hermes/skills/<category>/<name>/SKILL.md` — created via `skill_manage(action='create')`.
2. **In-repo:** `/path/to/hermes-agent/skills/<category>/<name>/SKILL.md` — committed, shipped with the package.

### Required Frontmatter

```yaml
---
name: <kebab-case-name>
description: "One-line description"
version: 1.0.0
author: Your Name
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tag1, tag2]
    related_skills: [other-skill]
---
```

### Structure Rules

- **Name:** kebab-case, lowercase, max 64 chars. Must be unique.
- **Body:** Start with `# Title`, then `##` sections. Keep under 20KB; if larger, split detail into `references/<topic>.md`.
- **Support files:** `references/`, `templates/`, `scripts/`, `assets/` subdirectories beside `SKILL.md`.
- **Validation:** Run the validator script after creation/editing:
  ```bash
  python /path/to/hermes-agent/scripts/validate_skills.py
  ```
- **Commit:** In-repo skills must be `git add`ed. Use `write_file` / `patch`, then commit.

### What Makes a Good Skill

- Captures a reusable workflow, not a one-off task
- Has clear trigger conditions (when to load it)
- Includes numbered steps with exact commands
- Has a Pitfalls section with common mistakes
- Has verification steps (how to confirm it worked)

---

## Skin Customization

Hermes terminal appearance is controlled by YAML skin files under `~/.hermes/skins/`.

### Quick Start

```bash
# Set active skin in config
hermes config set display.skin mytheme

# Create a new skin
cp ~/.hermes/skins/default.yaml ~/.hermes/skins/mytheme.yaml
# Edit name: mytheme at the top, then customize colors/spinner/banner
```

### Skin YAML Structure

```yaml
name: mytheme
description: My custom theme

colors:
  primary: "#FF6B6B"
  secondary: "#4ECDC4"
  accent: "#FFE66D"
  text: "#F7FFF7"
  background: "#1A1A2E"
  error: "#FF6B6B"
  success: "#4ECDC4"
  warning: "#FFE66D"
  info: "#45B7D1"

branding:
  response_label: "🤖"          # icon next to "Hermes"
  prompt_symbol: "❯"            # prompt character
  goodbye_message: "Goodbye!"

spinner:
  style: dots                    # dots, line, arrow, etc.
  speed: 80                      # ms between frames
```

### Key Customization Points

| Element | YAML Key | Description |
|---------|----------|-------------|
| Response icon | `branding.response_label` | Emoji/character next to "Hermes" |
| Prompt symbol | `branding.prompt_symbol` | The `>` or `❯` before user input |
| Goodbye | `branding.goodbye_message` | Exit message |
| Colors | `colors.*` | Hex codes (quoted — bare `#` is YAML comment) |
| Spinner | `spinner.style` / `spinner.speed` | Animation style and speed |

**Important:** Quote hex colors: `"#FF6B6B"`. Bare `#FF6B6B` is a YAML comment.

### Common Issues

- **Blank box instead of icon** → The terminal font lacks the glyph. Switch to a Nerd Font or use a simpler emoji.
- **Skin not applying** → Restart Hermes after editing. Check `hermes config get display.skin`.
- **Colors look wrong** → Terminal emulator color profile. Try True Color: `export COLORTERM=truecolor`.

---

## Fast-Mode Provider Extensions

Hermes has a `/fast` slash command that injects provider-specific overrides for higher-priority/faster serving.

### Architecture

```
agent fast toggle ON
   └─> resolve_fast_mode_overrides(model_id)  [hermes_cli/models.py]
         ├─ model_supports_fast_mode()  → gate; bool
         ├─ _is_<provider>_fast_model() → which matcher matched
         └─ returns {"service_tier": "priority"} | {"speed": "fast"} | None
   └─> injected into agent.request_overrides
   └─> consumed by _build_api_kwargs → API client kwargs
```

### Adding a New Provider

1. **Add matcher** in `hermes_cli/models.py`:
   ```python
   def _is_newprovider_fast_model(model_id: str) -> bool:
       return model_id.startswith("newprovider/") and "-fast" in model_id
   ```

2. **Register matcher** in `model_supports_fast_mode()`:
   ```python
   if _is_newprovider_fast_model(model_id):
       return True
   ```

3. **Add resolver** in `resolve_fast_mode_overrides()`:
   ```python
   if _is_newprovider_fast_model(model_id):
       return {"priority": "high"}  # provider-specific key-value
   ```

4. **Update adapter** if the provider uses a non-standard SDK (e.g., Anthropic's `speed: "fast"` needs handling in `agent/anthropic_adapter.py`).

5. **Add tests** in `tests/cli/test_fast_command.py`:
   ```python
   def test_fast_mode_newprovider():
       assert resolve_fast_mode_overrides("newprovider/fast-v1") == {"priority": "high"}
   ```

6. **Update docs** in the `hermes-fast-mode-providers` skill (or this section).

### Current Provider Support

| Provider | Override Key | Matcher Pattern |
|----------|-------------|-----------------|
| OpenAI | `service_tier: "priority"` | `gpt-4.5*` or `o3*` |
| Anthropic | `speed: "fast"` | `claude-opus-4-6*` |
| Fireworks | `priority: "high"` | `accounts/fireworks/models/*` |

---

## Plugin Development

Hermes plugins are standalone Python packages that register hooks, commands, and middleware without modifying core files. They live in `~/.hermes/plugins/<name>/` and are auto-discovered at startup.

### Plugin Structure

```
~/.hermes/plugins/my_plugin/
├── __init__.py       # Entry point — defines register(ctx)
└── plugin.yaml       # Optional manifest (name, version, description)
```

### The `register(ctx)` Entry Point

```python
def register(ctx) -> None:
    ctx.register_hook("hook_name", callback)
    ctx.register_command("/cmd", handler=fn, description="...")
```

**Available hooks** (`VALID_HOOKS` in `hermes_cli/plugins.py`):
`pre_tool_call`, `post_tool_call`, `transform_terminal_output`, `transform_tool_result`, `transform_llm_output`, `pre_llm_call`, `post_llm_call`, `pre_api_request`, `post_api_request`, `api_request_error`, `on_session_start`, `on_session_end`, `on_session_finalize`, `on_session_reset`, `subagent_start`, `subagent_stop`, `status_bar_fragment`, `pre_gateway_dispatch`, `pre_approval_request`, `post_approval_response`.

**Return-value semantics:**
- Most hooks are observers — return values ignored.
- `transform_*` hooks: first non-`None` string wins (can rewrite output).
- `status_bar_fragment`: return `[(style, text), ...]` to inject fragments, or `[]`/`None` for no contribution.
- `pre_gateway_dispatch`: return `{"action": "skip"}`, `{"action": "rewrite", "text": "..."}`, or `{"action": "allow"}`.

### Worked Example: TPS Counter (Status Bar Plugin)

A plugin that shows real-time tokens/second in the CLI status bar.

**1. Plugin code** (`~/.hermes/plugins/tps_monitor/__init__.py`):

```python
"""tps_monitor — show ⚡ 42 tok/s in the Hermes status bar."""

from __future__ import annotations
from typing import Any, List, Tuple

_STALE_AFTER_SEC = 5.0


def _format_tps(tps: float) -> str:
    if tps >= 100:
        return f"⚡ {int(tps)} tok/s"
    if tps >= 10:
        return f"⚡ {tps:.0f} tok/s"
    return f"⚡ {tps:.1f} tok/s"


def _on_status_bar_fragment(cli: Any = None, agent: Any = None, **_: Any):
    if agent is None:
        return []
    tps = getattr(agent, "_current_tps", 0.0) or 0.0
    last = getattr(agent, "_last_tps_update", 0.0) or 0.0
    if tps <= 0 or last <= 0:
        return []
    import time

    if time.time() - last > _STALE_AFTER_SEC:
        return []
    return [("class:status-bar-strong", _format_tps(tps))]


def register(ctx) -> None:
    ctx.register_hook("status_bar_fragment", _on_status_bar_fragment)
```

**2. Enable the plugin:**

```bash
hermes plugins enable tps_monitor
```

**What is upstream vs. what requires a core edit:**

- ✅ `status_bar_fragment` hook — already in upstream `VALID_HOOKS`; dispatched from `cli.py` `_get_status_bar_fragments()`.
- ✅ Plugin loading from `~/.hermes/plugins/` — fully upstream.
- ❌ `agent._current_tps` data source — **not upstream**. The built-in agent does not populate `_current_tps` or `_last_tps_update`. If you want a TPS readout, you must add the tracking code to `run_agent.py` and `agent_init.py` (see below). If you only need `status_bar_fragment` for other data, no core edits are required.

**Core edits required for TPS data only:**

These edits live inside the git repo at `~/.hermes/hermes-agent/` and are **at risk** on `hermes update`. They are auto-stashed before `git pull` and restored after, but if upstream changed the same lines, the stash restore will conflict.

- **`run_agent.py`** — add TPS tracking state + recorder:
  ```python
  # In reset_session_state():
  self._tps_token_count = 0
  self._tps_window_start = time.time()
  self._current_tps = 0.0
  self._last_tps_update = 0.0


  # New method:
  def _record_tps_token(self, text: str) -> None:
      """Track tokens-per-second using a rolling window."""
      if not text:
          return
      now = time.time()
      # Approximate token count: ~4 chars per token (works well for English/CJK mix)
      token_estimate = max(1, len(text) // 4)
      self._tps_token_count += token_estimate
      elapsed = now - self._tps_window_start
      # Update TPS immediately so the status bar shows something even for
      # fast responses.  The 1-second gate below is just for resetting the
      # window to keep the rolling average fresh.
      if elapsed > 0:
          self._current_tps = self._tps_token_count / elapsed
          self._last_tps_update = now
      if elapsed >= 1.0:
          self._tps_token_count = 0
          self._tps_window_start = now


  # In _fire_stream_delta(), at the top:
  self._record_tps_token(text)

  # In _fire_reasoning_delta(), at the top (reasoning/thinking text also counts):
  self._record_tps_token(text)

  # In chat_completion_helpers.py, suppressed content during tool calls also counts:
  agent._record_tps_token(delta.content)

  # In chat_completion_helpers.py, tool call JSON argument deltas also count:
  agent._record_tps_token(tc_delta.function.arguments)
  ```

- **`agent_init.py`** — mirror the init in `initialize_agent_instance()`:
  ```python
  agent._tps_token_count = 0
  agent._tps_window_start = time.time()
  agent._current_tps = 0.0
  agent._last_tps_update = 0.0
  ```

**Protecting core edits from `hermes update`**

Because these edits are inside the git repo, `hermes update` will stash them, pull, and restore. If upstream touched the same files, the restore may fail. The safe approach is a dedicated branch workflow.

---

### What `hermes update` actually does

`hermes update` runs inside `~/.hermes/hermes-agent/` (the git repo). The sequence is:

1. Stash any uncommitted changes on the current branch
2. If you're not on the target branch (default `main`), switch to it
3. `git fetch origin <branch>` then `git pull --ff-only origin <branch>`
4. If fast-forward fails, `git reset --hard origin/<branch>`
5. Restore stashed changes
6. Reinstall Python dependencies, rebuild UI

**Critical:** if you're on a custom branch when you run `hermes update`, it switches away to `main`, updates **with main's dependency pins**, and does **not** return to your branch. Your custom branch is left behind — and the venv is left pinned against the wrong branch. On this machine's checkout (`HERMES_HOME=/mnt/z/pantheon/.hermes`), **never run bare `hermes update`** — use `/mnt/z/pantheon/.hermes/scripts/safe_hermes_update.sh` instead (see Strategy A below).

---

### Strategy A: Local branch workflow (recommended)

This is the cleanest approach when you don't need a GitHub fork.

**One-time setup:**

```bash
cd ~/.hermes/hermes-agent
git checkout -b znh/custom
git add -A
git commit -m "znh: customisations snapshot"
git checkout main
```

**Every update — run the wrapper (it includes the rebase + dep re-sync):**

```bash
/mnt/z/pantheon/.hermes/scripts/safe_hermes_update.sh
# It: checks out main, runs `hermes update --yes`, returns to znh/custom
# (EXIT trap even on failure), rebases, re-syncs znh/custom's pins into
# BOTH venv/ (gateway) and .venv/, verifies, restarts the gateway.
# If the rebase conflicts it stops with instructions — resolve, re-run.
```

Manual equivalent (only if bypassing the wrapper — note the dep re-sync the
bare workflow historically forgot, causing the 2026-08-22 incident):

```bash
cd ~/.hermes/hermes-agent
hermes update                       # only from main; lands you on main
git checkout znh/custom
git rebase main
VIRTUAL_ENV=$PWD/venv  uv pip install -e '.[all]'   # gateway venv
VIRTUAL_ENV=$PWD/.venv uv pip install -e '.[all]'   # uv default venv
systemctl --user restart pantheon-hermes-gateway.service
```

**Why this works:**

- `main` stays clean — `hermes update` can switch to it, pull, and leave without touching `znh/custom`
- Your commits are preserved on `znh/custom` and replayed on top of fresh `main`
- If a rebase conflict happens, you resolve it once per upstream change, not once per file

**Adding new customisations:**

```bash
cd ~/.hermes/hermes-agent
git checkout znh/custom
# ... make edits ...
git add <files>
git commit -m "Add XYZ customisation"
git checkout main
```

---

### Strategy B: GitHub fork workflow

If you want your customisations backed up on GitHub or shared:

1. Fork `NousResearch/hermes-agent`
2. `git remote rename origin upstream`
3. `git remote add origin https://github.com/YOURUSER/hermes-agent.git`
4. Push `znh/custom` to your fork
5. Keep `main` synced with `upstream`, rebase `znh/custom` on top

`hermes update` does **not** auto-sync with upstream when you're on a fork — it only pulls from `origin`. You must manually sync `main` before updating.

---

### Strategy C: Post-update patch file

For a small number of edits, keep a `.patch`:

```bash
cd ~/.hermes/hermes-agent
git diff main znh/custom -- <files> > ~/tps-core.patch
# after hermes update:
git apply ~/tps-core.patch
```

Good for quick fixes, but becomes painful as customisations grow.

---

### What is safe without any strategy

These locations are **outside the git repo** and survive `hermes update` automatically:

| Location | What lives there |
|----------|-----------------|
| `~/.hermes/config.yaml` | Settings |
| `~/.hermes/.env` | API keys |
| `~/.hermes/skills/` | Skills |
| `~/.hermes/skins/` | Custom skins |
| `~/.hermes/plugins/` | Plugins (including `tps_monitor`) |
| `~/.hermes/memories/` | Persistent memory |
| `~/.hermes/cron/` | Scheduled jobs |
| `~/.hermes/state.db` | Session history |
| `~/.hermes/profiles/` | Other profiles |

**Rule of thumb:** if it's in `~/.hermes/` but **not** inside `hermes-agent/`, it's safe.

---

### Full workflow reference

See `references/hermes-core-customisation-workflow.md` for the complete documented workflow, troubleshooting, and migration to a fork.

### Observability Plugins

Hermes already ships with a reference observability plugin at `plugins/observability/langfuse/`. When adding tracing (e.g. Arize Phoenix OTel), follow the same hook-based pattern rather than monkey-patching OpenAI clients or modifying core files.

**Why hooks, not monkey-patches:**
- Hooks are stable API surfaces — monkey-patches break on SDK updates
- Hooks already fire at the exact instrumentation points you need
- No core edits means no rebase conflicts after `hermes update`

**Key hooks for LLM/tool tracing:**

| Hook | Fires | Use for |
|------|-------|---------|
| `pre_api_request` | Before every LLM API call | Start span, capture request metadata |
| `post_api_request` | After every LLM API call | End span, record usage, cost, finish reason |
| `pre_tool_call` | Before tool execution | Start tool span |
| `post_tool_call` | After tool execution | End tool span, record result/error |

**Critical architectural rule: instrument the API call, not the subprocess.** A span named `llm.invoke` that wraps a Claude Code subprocess (`sandbox_mgr.run_sandboxed()`) is misleading — that subprocess runs for minutes and makes dozens of its own LLM calls internally. The real LLM call happens where `chat.completions.create()` is invoked. Place spans at the API boundary, not the orchestration boundary.

**Cross-process trace propagation (Hermes → Pantheon workers):**
When Hermes triggers a Pantheon tool that spawns a worker process, the worker runs in a separate Python process with its own tracer. To keep spans connected:

1. In the Hermes plugin's `pre_tool_call` hook, inject the current W3C trace context into the tool's environment:
   ```python
   from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

   carrier = {}
   TraceContextTextMapPropagator().inject(carrier)
   env["TRACEPARENT"] = carrier.get("traceparent")
   ```

2. In the Pantheon worker, on startup, read `TRACEPARENT` from `os.environ` and attach it as the parent context before creating any spans:
   ```python
   from opentelemetry.context import attach, detach
   from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

   traceparent = os.environ.get("TRACEPARENT")
   if traceparent:
       carrier = {"traceparent": traceparent}
       ctx = TraceContextTextMapPropagator().extract(carrier)
       token = attach(ctx)
       # ... worker creates child spans here ...
       detach(token)
   ```

See `references/phoenix-otel-plugin-pattern.md` for the full reference implementation pattern copied from the existing Langfuse plugin.

### Programmatic Plugin Enablement

Plugins can be enabled programmatically without the CLI. This is useful for setup scripts that install and enable a plugin in one step:

```python
from hermes_cli.plugins_cmd import _get_enabled_set, _save_enabled_set

enabled = _get_enabled_set()
enabled.add("observability/phoenix")
enabled.add("security")
_save_enabled_set(enabled)
```

**Note:** Changes only take effect after a full Hermes restart.

### Security Plugins (pre_tool_call blocking)

Plugins can block dangerous tool calls by returning a block dict from `pre_tool_call`:

```python
def on_pre_tool_call(tool_name: str, args: dict, tool_call_id: str, **kwargs):
    command = args.get("command", "")

    # Block dangerous patterns
    if "rm -rf /" in command:
        return {"action": "block", "message": "SECURITY BLOCK: rm -rf / is not allowed"}

    # Warn but allow
    if "curl" in command and "| bash" in command:
        return {
            "action": "warn",
            "message": "WARNING: Remote script execution detected",
        }

    return None  # Allow
```

**Return-value semantics for `pre_tool_call`:**
- `None` or no return → allow execution
- `{"action": "block", "message": "..."}` → block with message shown to user
- `{"action": "warn", "message": "..."}` → allow but show warning

### Plugins with External Binaries

When a plugin needs external binaries (ShellCheck, vet, playwright, ffmpeg), do not commit them to git. Use the auto-download pattern:

1. Add binary names to `.gitignore`
2. Create `download_binaries.py` that fetches the right binary for the current platform
3. In `__init__.py`, check local → PATH → auto-download in that order
4. Swallow download exceptions gracefully — the plugin works without the binary

See `references/hermes-plugin-binary-download.md` for the full pattern.

### Pitfalls

- **Rolling-window counters: update the display value on every tick, not just at window boundaries.** A TPS tracker that only computes `_current_tps` after a full 1-second window will show nothing for fast responses that finish before the boundary. Compute the rate on every chunk and reset the accumulator only at the boundary.
- **Burst-artifact suppression.** The built-in `_record_tps_token` uses a 1-second rolling window with `tokens / elapsed_since_window_start`. Early in the window a small chunk can spike transiently (e.g. 25 tokens at 0.01 s = 2500 TPS). This settles as the window fills. For status-bar display, cap the shown value or accept that fast models (Kimi K2.6, Claude 4) can legitimately hit 100-300 tok/s and the meter will briefly overshoot before stabilising.
- **Width-overflow trim must run AFTER the plugin hook, not before.** In `cli.py`, the status-bar width check (`total_width > width`) must happen after plugin fragments are injected. If the trim runs first, a wide base status bar silently discards all plugin fragments without ever invoking the hook.
- **Track tokens on ALL text paths, not just `_fire_stream_delta`.** Model-generated text flows through three paths: regular content (`_fire_stream_delta`), reasoning/thinking blocks (`_fire_reasoning_delta`), and tool-call JSON argument accumulation (`chat_completion_helpers.py`). The TPS meter will undercount significantly if `_record_tps_token` is only called from `_fire_stream_delta`. All three paths must instrument the recorder.
- **Core file edits are ephemeral.** Any manual edit to `run_agent.py`, `cli.py`, or `hermes_cli/plugins.py` in the core package gets stashed during `hermes update` and restored after. If the upstream file changed in the same region, the stash restore will conflict and your changes remain in the stash. You'll need to `git stash apply` manually or use a branch-based workflow.
- **Plugins are opt-in.** Standalone plugins (in `~/.hermes/plugins/`) must be added to `plugins.enabled` in `config.yaml` — they do not auto-enable. Use `hermes plugins enable <name>`.
- **Plugin discovery ≠ plugin activation.** `discover_and_load()` may find the plugin and load its module, but if it's not in `plugins.enabled`, `enabled` will be `False`, `hooks_registered` will be empty, and `register()` is never called. Always verify with `hermes plugins list` or check `pm._plugins['<name>'].enabled`.
- **Plugin directory location follows `HERMES_HOME`.** If `HERMES_HOME` is set, the plugin scanner looks at `$HERMES_HOME/plugins/`, not `~/.hermes/plugins/`.
- **Restart required.** Core hook changes and new plugins only take effect after a full restart (`/exit` + `hermes`). Python caches imports; hot-reload won't pick them up.

---

## Related Skills

- `hermes-agent` — User setup, configuration, CLI reference, troubleshooting.
- `hermes-external-integration` — Integrating Hermes with external agent frameworks (Agno, etc.).
