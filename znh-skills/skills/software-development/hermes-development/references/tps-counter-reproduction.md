# TPS Counter Plugin — Full Reproduction Recipe

Session: 2025-06-23 (regression after core update)
Symptom: `tps_monitor` plugin enabled but no TPS shown in status bar.
Root cause: Core hermes-agent files updated via `git pull`; manual hook infrastructure edits wiped.

---

## Bug Fix: TPS Missing for Thoughts and Tool Calls (2026-06-24)

**Symptom:** TPS meter works for regular assistant text but shows nothing during reasoning/thinking blocks or while the model generates tool call arguments.

**Root cause:** `_record_tps_token` was only called from `_fire_stream_delta`. Model text also arrives via `_fire_reasoning_delta` and tool-call JSON argument deltas, neither of which recorded tokens.

**Fix:** Add `_record_tps_token` calls to all text-producing paths:

1. `run_agent.py` — `_fire_reasoning_delta`, at the top:
   ```python
   def _fire_reasoning_delta(self, text: str) -> None:
       self._record_tps_token(text)
       cb = self.reasoning_callback
       ...
   ```

2. `agent/chat_completion_helpers.py` — Suppressed content during active tool calls:
   ```python
   elif agent.stream_delta_callback:
       try:
           agent.stream_delta_callback(delta.content)
           agent._record_streamed_assistant_text(delta.content)
           agent._record_tps_token(delta.content)  # <-- added
       except Exception:
           pass
   ```

3. `agent/chat_completion_helpers.py` — Tool call JSON argument accumulation:
   ```python
   if tc_delta.function.arguments:
       entry["function"]["arguments"] += tc_delta.function.arguments
       agent._record_tps_token(tc_delta.function.arguments)  # <-- added
   ```

This ensures the TPS meter shows for every token the model generates, regardless of whether it is regular text, reasoning, or tool-call JSON.

---

## Bug Fix: Plugin Fragments Silently Dropped by Width Check (2026-06-24)

**Symptom:** Plugin enabled, `_current_tps` populated, hook returns fragments, but TPS still never appears in the status bar.

**Root cause:** In `cli.py`, `_get_status_bar_fragments()` computed `total_width` and ran the overflow trim **before** invoking the `status_bar_fragment` plugin hook. When the base status bar (model, context, duration, background tasks, etc.) was already wider than the terminal, the function returned a trimmed single-line status bar and never called the hook at all.

**Fix:** Move the plugin hook dispatch **before** the width-overflow check:

```python
# BEFORE (hook after trim — plugins silently discarded)
total_width = sum(self._status_bar_display_width(text) for _, text in frags)
if total_width > width:
    ...
    return [("class:status-bar", trimmed)]

# Plugin hook here — never reached if base bar overflows
plugin_frags = invoke_hook("status_bar_fragment", ...)

# AFTER (hook before trim — plugins included in width calculation)
plugin_frags = invoke_hook("status_bar_fragment", ...)
# ... append plugin fragments to frags ...

total_width = sum(self._status_bar_display_width(text) for _, text in frags)
if total_width > width:
    ...
    return [("class:status-bar", trimmed)]
```

---

## Bug Fix: Fast Responses Never Show TPS (2025-06-24)

**Symptom:** Plugin enabled, hook fires, `_current_tps` exists on the agent, but status bar shows nothing during streaming.

**Root cause:** `_record_tps_token` only assigned `_current_tps` after `elapsed >= 1.0`. Fast responses finish before the 1-second window elapses, so the value stays `0.0` and the plugin returns `None`.

**Fix:** Update `_current_tps` on every chunk (not just after 1 second). Reset the rolling window only after 1 second.

```python
# BEFORE (buggy — only updates after 1 second)
if elapsed >= 1.0:
    self._current_tps = self._tps_token_count / elapsed
    self._last_tps_update = now
    self._tps_token_count = 0
    self._tps_window_start = now

# AFTER (fixed — updates every chunk)
if elapsed > 0:
    self._current_tps = self._tps_token_count / elapsed
    self._last_tps_update = now
if elapsed >= 1.0:
    self._tps_token_count = 0
    self._tps_window_start = now
```

With this change the TPS meter appears immediately as soon as the first token chunk arrives, rather than waiting a full second.

---

## Files Changed (4 total)

### 1. `run_agent.py` — TPS tracking state

Add to `reset_session_state()` after `_user_turn_count`:

```python
# TPS (tokens per second) tracking
self._tps_token_count = 0
self._tps_window_start = time.time()
self._current_tps = 0.0
self._last_tps_update = 0.0
```

Add new method before `_fire_stream_delta`:

```python
def _record_tps_token(self, text: str) -> None:
    """Track tokens-per-second using a 1-second rolling window."""
    if not text:
        return
    now = time.time()
    # Approximate token count: ~4 chars per token
    token_estimate = max(1, len(text) // 4)
    self._tps_token_count += token_estimate
    elapsed = now - self._tps_window_start
    if elapsed >= 1.0:
        self._current_tps = self._tps_token_count / elapsed
        self._last_tps_update = now
        self._tps_token_count = 0
        self._tps_window_start = now
```

Add call inside `_fire_stream_delta`, at the very top:

```python
def _fire_stream_delta(self, text: str) -> None:
    """Fire all registered stream delta callbacks (display + TTS)."""
    # Track TPS for status bar display
    self._record_tps_token(text)
```

### 2. `hermes_cli/plugins.py` — Hook registry

Add `"status_bar_fragment"` to `VALID_HOOKS`:

```python
VALID_HOOKS: Set[str] = {
    # ... existing hooks ...
    "subagent_start",
    "subagent_stop",
    # Status bar fragment hook. Fires every render tick when the TUI status bar
    # is visible. Plugins return a list of (style, text) tuples to inject into
    # the status bar, or None/empty list for no contribution.
    "status_bar_fragment",
    # ... rest of hooks ...
}
```

### 3. `cli.py` — Hook dispatch

Inside `_get_status_bar_fragments()`, after the width-overflow check and before `return frags`:

```python
# ── Plugin status_bar_fragment hook ────────────────────────
# Plugins (e.g. tps_monitor) can inject extra fragments here.
try:
    from hermes_cli.plugins import invoke_hook

    plugin_frags = invoke_hook(
        "status_bar_fragment",
        cli=self,
        agent=getattr(self, "agent", None),
    )
    for pf in plugin_frags or []:
        if isinstance(pf, (list, tuple)) and len(pf) == 2:
            frag_text = pf[1] if isinstance(pf[1], str) else str(pf[1])
            if self._status_bar_display_width(frag_text) > 0:
                frags.append(("class:status-bar-dim", " │ "))
                frags.append(pf)
except Exception:
    pass
```

### 4. Plugin directory — survives updates

`~/.hermes/plugins/tps_monitor/__init__.py` (already in place, see SKILL.md body).

---

## Verification After Re-apply

```bash
python3 -c "
import ast
for f in [
    'hermes_cli/plugins.py',
    'cli.py',
    'run_agent.py',
    '~/.hermes/plugins/tps_monitor/__init__.py',
]:
    try:
        ast.parse(open(f).read())
        print(f'  {f} syntax OK')
    except SyntaxError as e:
        print(f'  {f}: {e}')
"
```

Check config:
```bash
grep "tps_monitor" ~/.hermes/config.yaml
# Expected: "  - tps_monitor" under plugins.enabled
```

Restart required: `/exit` then `hermes`.

---

## Future-Proofing Options

1. **Contribute upstream** — Open a PR adding `status_bar_fragment` to `VALID_HOOKS` and the dispatch call in `_get_status_bar_fragments()`. The TPS tracking state in `run_agent.py` could also be upstreamed, or kept as a user plugin that reads `agent.session_output_tokens` + elapsed time instead of a custom rolling window.

2. **Post-update script** — Keep a shell script that re-applies the 3 core-file patches after every `git pull` in `~/.hermes/hermes-agent/`.

3. **Pure-plugin approach** — Redesign to use only existing hooks. For example, `post_api_request` could track timestamps and compute TPS from `session_output_tokens`, avoiding core edits entirely. Less precise (not per-delta) but survives updates.
