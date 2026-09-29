# znh-plugins

Zack's Hermes plugins. **Not upstream** — these exist only in this fork, and
before 2026-08-17 they existed only as untracked files under
`/mnt/z/pantheon/.hermes/plugins/`, with no history and no way to restore them.

They are load-bearing for the Pantheon dispatch pipeline, so losing them would
break agent dispatch rather than merely degrade it.

## Install

```bash
./znh-plugins/install.sh          # symlinks each plugin into $HERMES_HOME/plugins
hermes plugins list               # each should read: enabled / user
```

`HERMES_HOME` defaults to `/mnt/z/pantheon/.hermes` (the live home). Note there
is a stale `/home/znh/.hermes` that a bare `hermes` invocation picks up when
nothing sets `HERMES_HOME` — it has an empty `plugins/` and is not what you
want.

A plugin must also be listed in `config.yaml` under `plugins.enabled`; plugins
are opt-in, so a correctly linked plugin that is absent from that list silently
does nothing.

## Why symlinks rather than living in `plugins/`

Hermes scans three roots (`hermes_cli/plugins.py` ~:1367-1395): the repo's
`plugins/` as `bundled`, `$HERMES_HOME/plugins` as `user`, and optionally a
project dir. Dropping these into the repo's `plugins/` would work with no
symlinks at all, but it mixes 6 personal plugins into upstream's 22 — noisier
merges, and they would be reported as `bundled` when they are anything but.

The scanner has no `is_symlink()` guard, so symlinking is safe. (The *platform*
loader at `gateway/platforms/base.py:1271` does skip symlinks — don't use this
pattern there.)

## What's here

| Plugin | Purpose |
|---|---|
| `herdr_bridge` | Reports real Hermes lifecycle state to the enclosing herdr pane. Its `pre_approval_request` hook is the reason a headless approval prompt shows as `blocked` instead of silently timing out and denying. |
| `opencode_worker` | `opencode_delegate` tool. Spawns delegated OpenCode runs into a child herdr pane (`pane split` off the parent) rather than a captured pipe. |
| `herdr-agent-state` | herdr's own stock integration. Third-party — `herdr integration install hermes` will overwrite it, so treat this copy as a snapshot, not the source of truth. |
| `task_completion_guard` | Blocks completion claims that show no OpenCode delegation. |
| `process_completion_log` | Records process completions. |
| `tps_monitor` | Live tokens/sec display. |

## Caveat

`herdr_bridge/tests/` runs against the plugin in place. The suite for
`opencode_worker`'s herdr lane lives in this repo at
`tests/plugins/test_opencode_worker_herdr.py` and skips when the deployed
plugin path is absent — so it tests through the symlink, not this directory
directly.
