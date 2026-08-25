# Hung-on-model-stream diagnostic — 2026-08-16 (Pantheon ntfy fix)

Part of delegaled-run-verification. This is the concrete walkthrough behind the
"hung-on-model-stream variant" section. The run appeared healthy but had been
silent for ~11 minutes.

## What "healthy but stalled" looked like

- `ps -o pid,etime,%cpu,stat -p 2159994`
  → `10:49  3.9  Sl+` — alive, but `%CPU` is a *lifetime average*, not proof of
  current work.
- CPU-tick sampling showed the truth:
  ```
  sample 1: utime+stime=2615
  sample 2: utime+stime=2618     # +3 ticks over ~2s of wall
  sample 3: utime+stime=2619     # +1 tick
  ```
  ~4 ticks / 4 s ≈ 40 ms CPU over 4 s → essentially idle. Combined with
  `State: S (sleeping)` and wchan `ep_poll`, that is waiting on I/O/network,
  not computing. `ps -o pid,etime,%cpu,stat,cmd` + `/proc/<pid>/wchan` +
  `/proc/<pid>/status` (`State`, `Threads`) give the full picture.

## Red herring: "it wrote files in the last 30 min"

`find <repo> -newermt "-30 minutes" -type f` returned almost nothing but:
- `.venv/lib/python3.12/site-packages/**/*.pyc`
- `.pytest_cache/v/cache/{lastfailed,nodeids}`
- `.venv/bin/pantheon`

That is ONE earlier `uv run pytest` run's footprint, not ongoing work. The
critical check: **source-file mtimes vs process start time**.
`ps -o lstart -p <pid>` → process started 20:34. The real edits were:
```
ntfy.py            20:31:58   # BEFORE process start
secrets_manager.py 20:32:19
tests/test_*.py    20:32-33
conftest.py        20:33:13
```
All predate the run. So this process had done NO source editing; the edits were
a prior (crashed) run's. `.pyc` files are compiled test deps, not task output.

## Pinning the exact stall moment from opencode.log

`~/.local/share/opencode/log/opencode.log` is huge (18 MB) — read the tail and
grep for `message=stream` for the specific `run=<uuid>`:

```
... run=f252f153 message=stream providerID=synthetic modelID=hf:moonshotai/Kimi-K3
    session.id=ses_ff3ee7... messageID=msg_00c12adfa... agent=build mode=primary
... run=f252f153 message=loop session.id=ses_ff3ee7... step=10
... run=f252f153 message=stream providerID=synthetic modelID=hf:moonshotai/Kimi-K3 ...
```

The last `message=stream ... modelID=...` line IS the in-flight model call.
Here it was `19:35:59.691Z` and nothing for that `run=` logged after — a hung
stream. Everything after in the log was the server daemon's periodic
`event.type=catalog.updated` heartbeat for the same workspace dirs and an
`update check` — **noise, not agent work.**

Cross-check: `stat ~/.local/share/opencode/opencode.db` — last write exactly
matching the last stream timestamp (`20:35:59.676`) confirms the session store
went silent too.

## The default-model twist

The hung model `synthetic/Kimi-K3` is NOT listed under the `synthetic` or
`openrouter-nitro` provider models in `~/.config/opencode/opencode.json`
(which lists e.g. `hf:zai-org/GLM-5.2` for synthetic and many `:*:nitro` for
openrouter). So opencode resolved its *own* default to Kimi-K3 and hung there.
The resolved model is visible in the `> build · hf:...` banner and in the log's
`modelID=`. Lesson: do not assume the running model matches the config's first
listed model; verify from the log/banner, and pin `--model <known-good>` at
re-dispatch if the default has ever hung.

## Re-dispatch after kill

Through the kanban board (not the opencode_delegate bypass): create the card
with `vault_board.py upsert --status ready-for-agent --assignees OpenCode`, and
let `trigger_scanner.py` → `vault_kanban_dispatch.py` claim and run it. New
scratch dir + fresh brief are allocated on a fresh claim. Watch for a
double-dispatch (two `opencode run` PIDs for one card) — if the watcher sweep
and the polling observer both fire on the same claim, you get two writers on
the same files.
