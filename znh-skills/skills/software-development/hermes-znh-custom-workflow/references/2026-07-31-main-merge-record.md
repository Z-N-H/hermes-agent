# Merge Record: main → znh/custom (2026-07-31)

## Context

Hermes update from v0.16.0 (upstream f3cda0ce) to v0.19.1 (July 30, 2026 build).
The `znh/custom` branch carried 10 local commits vs upstream.

## Pre-Update State

- Branch: `znh/custom` with 10 carried commits (including `d8d0a590f0 znh: customisations snapshot`)
- Dirty working tree: 9 files modified (committed as `94da2de0db chore: working tree changes before upstream sync`)
- Upstream: `f3cda0ceb1` (Merge pull request #75218)

## Identity divergence

- Pre-update: `Hermes Agent v0.16.0 (2026.6.5) · upstream f3cda0ce · local 42d48bc3 (+8 carried commits)`
- Post-update: `Hermes Agent v0.19.1 (2026.7.30) · upstream f3cda0ce · local bc5e1d08 (+10 carried commits)`

## Conflicted Files (14)

Files we intentionally customized that had NO conflict (auto-merged clean):
- `agent/prompt_builder.py` ✅ (CRITICAL_BOUNDARY_GUIDANCE preserved)
- `agent/system_prompt.py` ✅
- `agent/agent_init.py` ✅
- `cron/scheduler.py` ✅
- `hermes_cli/plugins.py` ✅
- `plugins/memory/hindsight/__init__.py` ✅
- `tools/process_registry.py` ✅

Conflicted files — resolved with upstream (not our customisations):
- `agent/auxiliary_client.py` — theirs
- `agent/display.py` — theirs
- `agent/image_routing.py` — theirs
- `cli.py` — theirs
- `gateway/run.py` — theirs
- `hermes_cli/main.py` — theirs
- `hermes_cli/skin_engine.py` — theirs
- `package-lock.json` — theirs
- `run_agent.py` — theirs
- `tests/agent/test_display_emoji.py` — theirs
- `tests/tools/test_registry.py` — theirs
- `tools/send_message_tool.py` — theirs

Conflicted files — our customized files (resolved carefully):
- `hermes_cli/gateway.py` — conflict in systemd service template. Upstream added systemd type/watchdog support (`Type={systemd_type}`, `{systemd_watchdog_directives}`). Accepted upstream since it's a genuine improvement over our simpler `Type=simple`.

Modify/delete conflicts:
- `gateway/platforms/slack.py` — upstream deleted this file (Slack moved to `plugins/platforms/slack/`). We had modified it with syntax highlighting and Block Kit enhancements. **Accepted deletion** — our Slack customisations need manual porting to the plugin.

## Key Observations

1. **Version jump was large** (v0.16.0 → v0.19.1, 19502 commits). The merge conflict count (14 files) was reasonable for this divergence.
2. **Our core customisations auto-merged** on prompt_builder, system_prompt, agent_init — no conflict on the files that matter most.
3. **Slack moved to plugin.** This is a structural upstream change that invalidates our previous Slack patches. Porting Block Kit / syntax highlighting to `plugins/platforms/slack/` is future work.
4. **Merge approach worked better than rebase.** One conflict resolution session instead of replaying 10 commits. Merge commit `bc5e1d0834` cleanly separates "upstream changes" from "our patches."

## Post-Merge Incident: Silent Customization Loss (found + fixed same day)

The "Conflicted files — resolved with upstream" list above was treated as safe to discard
wholesale because none of `agent/display.py`, `cli.py`, `gateway/run.py`, `hermes_cli/main.py`,
`hermes_cli/skin_engine.py`, `run_agent.py`, or the two test files were on the SKILL.md
"Your customised files" list at merge time. In fact all of them carried real customizations:

1. `run_agent.py` lost `_record_tps_token` (and its call sites in `_fire_stream_delta`/
   `_fire_reasoning_delta`) — every streamed tool call raised `AttributeError`, which the
   streaming error handler misreported as a network error, permanently stalling tool calls
   (e.g. `session_search`) on retry.
2. `cli.py` lost the `status_bar_fragment` plugin-hook invocation in
   `_get_status_bar_fragments` — the `tps_monitor` plugin (in `.hermes/plugins/`, outside this
   repo) was completely intact but never got a chance to render.
3. The full emoji → Nerd Font icon system regressed: `cli.py` (brand icon at ~16 call sites,
   the `_apply_prompt_toolkit_tuple_style_patch` bugfix, `ICON_BOLT` tool-emoji default),
   `agent/display.py` (`get_tool_emoji`, all of `get_cute_tool_message`'s per-tool icons),
   `hermes_cli/skin_engine.py` (`status_bar_model` skin colors — `get_active_brand_icon` itself
   survived), `hermes_cli/gateway.py`, `hermes_cli/main.py`, `hermes_cli/agent_import.py`,
   `hermes_cli/cli_billing_mixin.py`, `gateway/run.py`'s tool-emoji default, and a brand-new
   file `hermes_cli/update_cmd.py` (split out of `main.py` by an upstream decomposition after
   the original patch was written, so it was never on any list and never conflicted).
   `tests/agent/test_display_emoji.py` and `tests/tools/test_registry.py` were wholesale
   replaced by upstream's version (confirmed byte-identical to `origin/main`), silently
   deleting several test methods along with their assertions.

Root cause: a **clean 3-way merge drops customizations with no conflict at all** when upstream
rewrites the surrounding function heavily enough — conflict resolution alone doesn't surface
this. Fixed same day: restored every call site by diffing the last known-good pre-merge commits
(`d8d0a590f0`, `94da2de0db`) against post-merge HEAD, reapplied at the new locations (not a
blind patch — several functions had legitimately evolved upstream in the interim). Also fixed
the process gap: `SKILL.md`'s customized-files list now includes all of the above, and
`scripts/verify_znh_customizations.py` (wired as `.git/hooks/post-merge`) checks structural
markers for every known customization plus runs the companion tests, so a repeat is caught
same-day instead of by the user noticing broken output.

## Commands Used

```bash
# 1. Pre-update commit
cd /mnt/z/pantheon/.hermes/hermes-agent
git add -u
git commit -m "chore: working tree changes before upstream sync"

# 2. Update (handles git + deps + web UI)
hermes update --yes

# 3. Merge upstream into custom branch
git checkout znh/custom
git merge main

# 4. Resolve conflicts
git checkout --theirs <non-custom-files> && git add <them>
git rm gateway/platforms/slack.py    # modified by us, deleted upstream
git checkout --theirs hermes_cli/gateway.py && git add hermes_cli/gateway.py
git commit -m "chore: merge upstream main into znh/custom"
```
