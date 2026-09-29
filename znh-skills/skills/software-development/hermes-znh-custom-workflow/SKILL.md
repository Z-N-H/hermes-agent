---
title: Hermes znh/custom Patch Branch Workflow
description: How to manage personal Hermes customizations on the znh/custom branch without losing them on upstream updates.
name: hermes-znh-custom-workflow
trigger:
  - user asks about Hermes branch workflow
  - user asks about merging PRs
  - user asks about hermes update
  - user asks about custom branch
  - user asks about znh/custom
  - user asks how to preserve customisations
  - user wants to update Hermes without losing changes
---

# Hermes `znh/custom` Patch Branch Workflow

## What `znh/custom` Is

A **local patch branch** inside `/mnt/z/pantheon/.hermes/hermes-agent/` for personal Hermes customizations:
- Plugins (e.g. `observability/phoenix`, `security`)
- Core patches (`prompt_builder.py`, `system_prompt.py`, `agent_init.py`)
- Slack gateway enhancements
- Skin customizations

**NOT synced upstream** to NousResearch/hermes-agent. The fork at `Z-N-H/hermes-agent` exists for backup/mirror only.

## Full Update Sequence (Merge Approach, Recommended)

> **Automated path (use this):** `/mnt/z/pantheon/.hermes/scripts/safe_hermes_update.sh`
> runs Step 2 through the rebase, dependency re-sync, verification, and gateway
> restart in one go, with hard guards against the two incident modes. The
> manual steps below still apply when the wrapper stops on a rebase conflict,
> or when you deliberately want a merge instead of a rebase. See Step 2.

This is the proven workflow — using `git merge` instead of rebase gives one conflict-resolution session instead of replaying N commits individually, and `hermes update` handles dependency reinstall + web UI rebuild automatically.

### Step 1: Pre-Update Hygiene

Before any update, commit ALL dirty changes on `znh/custom`:

```bash
cd /mnt/z/pantheon/.hermes/hermes-agent
git add -u
git commit -m "chore: working tree changes before upstream sync"
```

Skim `git status` for any new untracked files that should be tracked or gitignored.

### Step 2: Update via the safe wrapper — never bare `hermes update`

**Do NOT run bare `hermes update` on this checkout.** It assumes trunk-only
usage: it checks out `main`, pulls, installs **main's** dependency pins into
`venv/`, and on a successful update never switches back — leaving the venv
holding main's pins while `znh/custom` (with its own deliberate pins, e.g.
`mcp==1.26.0` vs main's `mcp==2.0.0`) is what should be checked out. This
broke every MCP tool call in the live gateway on 2026-08-22 (and caused
branch/shallow-clone chaos on 2026-07-31).

Use the wrapper instead:

```bash
/mnt/z/pantheon/.hermes/scripts/safe_hermes_update.sh
```

What it does (in order):
1. Preflight: fails unless you're on `znh/custom` with no staged/modified
   tracked files, not detached, no rebase/merge in progress.
2. `git checkout main`
3. `hermes update --yes` — hermes' full pipeline (fetch+pull, dep sync for
   main, web UI rebuild, skill sync, config migration, pre-update backup)
   runs against `main` and only `main`.
4. `git checkout znh/custom` — ALWAYS, even on failure (EXIT trap backstop).
5. `git rebase main` — replays your local commits onto the fresh main. On
   conflict it stops and leaves the rebase for you (see Step 4 below), then
   re-running the wrapper picks up from the dep sync.
6. Re-syncs deps from **znh/custom's** `pyproject.toml` into **every venv
   present** (`venv/` and `.venv/` — see "The Two Venvs" below) via
   `uv pip install -e '.[all]'`. This is the step whose absence caused the
   2026-08-22 incident.
7. Verifies: ends on `znh/custom`, no in-flight rebase, and the installed
   `mcp` version in each venv matches the pin in `pyproject.toml` — hard
   failure otherwise.
8. Runs `scripts/verify_znh_customizations.py` (Step 4.5's guard).
9. Restarts `pantheon-hermes-gateway.service` and scans the fresh boot
   window of `logs/mcp-stderr.log` + `logs/errors.log` for
   `AttributeError`/`ImportError` — fails loudly if found.

Options: `--dry-run` (print the plan, mutate nothing), `--no-restart`,
`--skip-guard`. If the rebase is clean, **Steps 3–5 below are already done
for you** — skip to the next section.

### Step 3: Merge Upstream Into `znh/custom`

```bash
git checkout znh/custom
git merge main
```

### Step 4: Resolve Conflicts

**Strategy: accept upstream for files you didn't intentionally customize.**

**⚠️ This list has gone stale before and silently cost real customizations — see the 2026-07-31 incident below. Do not trust a static list alone; treat it as a starting point and run the guard script (Step 4.5) to catch anything it misses.**

Classification:
- **Your customised files** — inspect each conflict and keep your changes where they're intentional customizations. Auto-merges may already get this right — verify CRITICAL_BOUNDARY_GUIDANCE and system prompt additions survived. Known customized files, grouped by what they carry:
  - Agent core / prompts: `agent/prompt_builder.py`, `agent/system_prompt.py`, `agent/agent_init.py` (TPS state init), `agent/chat_completion_helpers.py` (TPS token recording calls), `run_agent.py` (`_record_tps_token`, `_fire_stream_delta`/`_fire_reasoning_delta`)
  - Emoji → Nerd Font icon system: `hermes_icons.py` (the icon module itself — a whole new file, low conflict risk), `agent/display.py` (`get_tool_emoji`, `get_cute_tool_message`), `hermes_cli/skin_engine.py` (`get_active_brand_icon`, `status_bar_model` skin colors), `tools/registry.py` (`ICON_BOLT` default), `gateway/platforms/base.py`, `gateway/run.py` (`ICON_GEAR` tool-emoji defaults)
  - CLI/TUI brand icon call sites (all route through `get_active_brand_icon()` instead of hardcoding `"⚕"`): `cli.py` (banner, status bar at all width tiers, response labels, goodbye, prompt-working state, plus the `_apply_prompt_toolkit_tuple_style_patch` bugfix and the `status_bar_fragment` plugin-hook invocation), `hermes_cli/gateway.py`, `hermes_cli/main.py`, `hermes_cli/claw.py`, `hermes_cli/cli_commands_mixin.py`, `hermes_cli/cli_billing_mixin.py`, `hermes_cli/config.py`, `hermes_cli/setup.py`, `hermes_cli/setup_whatsapp_cloud.py`, `hermes_cli/status.py`, `hermes_cli/tools_config.py`, `hermes_cli/uninstall.py`, `hermes_cli/agent_import.py`, `hermes_cli/plugins.py` (`status_bar_fragment` in `VALID_HOOKS`)
  - **Watch for upstream code-decomposition moves**: upstream sometimes "mechanically" splits a god-file into new modules (e.g. `hermes_cli/main.py` → `hermes_cli/update_cmd.py` in July 2026). A customization inside the moved code lands in a **brand-new file that isn't on this list yet** and won't show as a conflict at all — it just silently reverts to the un-patched text. Grep for the customization's signature (`get_active_brand_icon`, `ICON_BOLT`, `hermes_icons`) across the whole repo after every merge, not just the files below.
  - Other: `cron/scheduler.py`, `plugins/memory/hindsight/__init__.py`, `plugins/observability/phoenix/__init__.py`, `tools/process_registry.py`
  - Companion tests (each is a full customized file, not a diff — restore by comparing against the last known-good pre-merge commit): `tests/test_hermes_icons.py`, `tests/agent/test_display_emoji.py`, `tests/tools/test_registry.py`
  - TUI frontend: `ui-tui/src/components/appChrome.tsx`, `ui-tui/src/components/appLayout.tsx`, `ui-tui/src/theme.ts`
- **Everything else** — accept upstream (`git checkout --theirs <file>`). You didn't touch these; upstream improvements should win.
- **Deleted-in-upstream files you modified** (e.g., `gateway/platforms/slack.py` was deleted when Slack moved to a plugin) — accept the deletion. Upstream moved the feature; re-apply your customizations in the new location if needed.
- **Generated files** (`package-lock.json`) — accept either side, these get regenerated.

Convenience command after classifying:
```bash
git checkout --theirs <file1> <file2> ... && git add <file1> <file2> ...
```

For modify/delete conflicts (UD status):
- Accept delete: `git rm <file>`
- Keep your version: `git add <file>`

### Step 4.5: Run the Customization Guard (Required)

A clean 3-way merge can silently drop a customization with **no conflict at all** if upstream rewrote the surrounding function heavily enough — this has already happened three times (TPS tracking, the status-bar plugin hook, and the emoji→Nerd-Font icon system, all on 2026-07-30/31). Conflict resolution alone is not sufficient verification.

```bash
cd /mnt/z/pantheon/.hermes/hermes-agent
./scripts/verify_znh_customizations.py
```

This checks structural markers for every known customization (not byte-identity, so it tolerates legitimate upstream changes around them) and runs the companion test files. It's also wired as `.git/hooks/post-merge`, so it fires automatically after `git merge`/`git pull` in this repo — but run it manually too after conflict resolution, since the hook fires on the merge commit, before you've hand-fixed anything.

### Step 5: Commit Merge + Verify

```bash
git commit -m "chore: merge upstream main into znh/custom"
```

Verify key customizations survived:
```bash
grep -c "CRITICAL_BOUNDARY_GUIDANCE" agent/prompt_builder.py
hermes --version        # should show new upstream version + your commit count
```

### Pitfalls

- **Don't skip Step 1.** Uncommitted dirty changes get stashed by `hermes update` but you lose visibility into what was pending.
- **Merge vs rebase:** This skill historically recommended `git rebase main`. The merge approach (Step 3) is preferred — one conflict resolution instead of replaying N commits, and `znh/custom`'s history stays cleanly bifurcated (custom patches vs upstream merges). Use rebase only if you want a linear history.
- **After Slack moved to a plugin** (upstream v0.19+), `gateway/platforms/slack.py` was deleted in main. If you had Slack customizations (syntax highlighting, Block Kit), they need manual re-application in `plugins/platforms/slack/`.
- **After merge, restart the Hermes gateway** for changes to take effect: `systemctl --user restart pantheon-hermes-gateway.service`.
- **A stale "customised files" list causes silent data loss, not just a missed conflict.** On 2026-07-31, `cli.py`, `run_agent.py`, `agent/display.py`, `hermes_cli/skin_engine.py` and several others were resolved with `git checkout --theirs` because they weren't on the list above at the time — discarding TPS tracking, the status-bar plugin hook, and the entire emoji→Nerd-Font icon system with no conflict markers to flag it. See `references/2026-07-31-main-merge-record.md` for the full incident and fix. Always run Step 4.5's guard script — don't rely on the list alone.

## The Two Venvs (`venv/` vs `.venv/`)

The checkout has **two** Python environments, and they can silently diverge:

- `venv/` — created by the Hermes installer; **this is what production runs
  from**. `pantheon-hermes-gateway.service`, the dashboard, and every other
  long-lived process use `venv/bin/python3` (it also says
  `prompt = hermes-agent` in its `pyvenv.cfg`).
- `.venv/` — `uv`'s default project environment, created as a side effect of
  any `uv sync` / `uv run` executed in the checkout (first seen 2026-07-22).
  No service uses it, but anything that *does* run via `uv run` here picks it
  up silently.

Resolution: **both are kept, both are synced.** `.venv/` self-heals into
existence whenever someone runs `uv sync`/`uv run`, so deleting it only buys
a quieter repo until the next accidental recreate. The danger is divergence,
not existence — `safe_hermes_update.sh` installs `znh/custom`'s pins into
**every venv directory that exists** and hard-fails if the installed `mcp`
version doesn't match the pin afterwards. Never run `uv pip install` /
`uv sync` in this checkout outside the wrapper unless you also sync the other
venv the same way.

## Post-Update Rebase (Alternative)

If you prefer a linear history, rebase instead of merge in Step 3:

```bash
cd /mnt/z/pantheon/.hermes/hermes-agent
git checkout znh/custom
git rebase main
```

This replays your customizations one commit at a time on top of the fresh upstream. Conflicts surface per-commit rather than all at once — more granular but more work.

## PR Rules

| Repo | PR Action | Why |
|------|-----------|-----|
| `Z-N-H/hermes-agent` (fork) | **Keep open / close without merging** | Merging would diverge `main` from upstream, making every future update messy |
| `Z-N-H/pantheon` (own repo) | **Merge into `master`** | This is your own project; merging is correct |

## When to Push

Push `znh/custom` to the fork after any significant commits:
```bash
git push znh-fork znh/custom
```

The fork PR is a **disaster recovery backup** — not a merge target.
