"""tps_monitor plugin — show real-time tokens/second in the Hermes status bar.

Tracks the rate of streamed output tokens by reading the agent's rolling
counter (populated in ``run_agent._fire_stream_delta``) and injects
styled fragments into the CLI status bar via the ``status_bar_fragment``
hook.

Returns a list of ``(style, text)`` tuples matching the existing status
bar convention: strong value + dim unit label.  The consumer in
``cli.py`` adds the ``│`` separator before the first fragment.

No configuration needed. Disable by removing the plugin directory.
"""

from __future__ import annotations

from typing import Any, List, Tuple


_STALE_AFTER_SEC = 5.0


def _format_tps_value(tps: float) -> str:
    if tps >= 100:
        return f" {int(tps)}"
    if tps >= 10:
        return f" {tps:.0f}"
    return f" {tps:.1f}"


def _on_status_bar_fragment(
    cli: Any = None,
    agent: Any = None,
    **_: Any,
) -> List[Tuple[str, str]] | None:
    if agent is None:
        return None

    tps = getattr(agent, "_current_tps", 0.0) or 0.0
    last_update = getattr(agent, "_last_tps_update", 0.0) or 0.0

    if tps <= 0:
        return None
    if last_update <= 0:
        return None

    import time

    age = time.time() - last_update
    if age > _STALE_AFTER_SEC:
        return None

    return [
        ("class:status-bar-strong", _format_tps_value(tps)),
        ("class:status-bar-dim", " tok/s"),
    ]


def register(ctx) -> None:
    ctx.register_hook("status_bar_fragment", _on_status_bar_fragment)
