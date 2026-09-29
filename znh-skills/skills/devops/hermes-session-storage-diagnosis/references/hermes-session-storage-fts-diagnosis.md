# Hermes "session storage could not be written" — full walkthrough

Real diagnostic session on the Pantheon box (**2026-08-09, the FTS-index-lag
incident**). Error under test:

> `:warning: No reply: the turn was stopped because session storage could not
> be written (the transcript would have been lost on restart). Check disk space
> / permissions for the state DB, then send your message again.`

This is a **session-persistence failure**, NOT a context-compaction notice.

> ⚠️ **Scope note (updated 2026-08-25, task 035):** This walkthrough documents
> the 2026-08-09 **per-session FTS-index-lag** case (cause B in SKILL.md). A
> later, larger incident (2026-08-24, ~21h of lost transcripts across ALL
> sessions) had the same user-visible warning but a completely different
> cause: **the nono sandbox denying SQLite's temp dir (/var/tmp), with
> access(2) lying about writability → SQLITE_CANTOPEN on every write**. That
> case was *misdiagnosed twice* using this file's conclusion — do not treat
> this document's "it's the FTS index" outcome as default. Classify first:
> if `max(messages.timestamp)` is frozen for every session while the gateway
> lives, it's the environment (cause A), not any FTS index.

## Key finding (this incident only)

The warning's guidance ("check disk space / permissions") is a red herring.
Disk, DB ownership, and permissions were all healthy. The real cause was the
**FTS5 index lagging the live in-memory history** — for ONE session, while
other sessions kept persisting. Confirmed by gateway.log:

```
2026-08-09 08:03:17,898 WARNING [sess] gateway.run: Persisted transcript lagged
live cached history for session agent:main:slack:dm:...:1786258838.455059
(disk=25, memory=26); preserving live conversation context (possible FTS write corruption)
2026-08-09 08:03:42,375 WARNING [sess] gateway.run: ... (disk=25, memory=28) ...
```
`memory` 26→28 while `disk` stuck at 25 across 30s = the lag.

## Commands run (with outputs)

1. Disk: `df -h /mnt/z /home` → 236G size, 136G used, **98G avail (59%)** — fine.
   `df -i` reads `0/0/0` on overlayfs — **ignore inodes**.

2. State DB + ownership:
   - `~/.hermes/state.db` = 446,447,616 bytes, owner `1000:1000`, mode `644`.
   - `id` → uid=1000; all Hermes processes (`hermes gateway`, `hindsight-api`,
     `hermes dashboard`) also run as uid 1000.
   - `test -w ...state.db` → WRITABLE.

3. SQLite health (via Python, no sqlite3 CLI):
   `integrity_check=ok`, `journal_mode=wal`, `busy_timeout=5000`.

4. FTS inventory in state.db:
   - `messages_fts` (FTS5 virtual, col `content`)
   - `messages_fts_trigram` (FTS5 virtual, col `content`, trigram tokenizer)
   - each with `_content/_data/_idx/_docsize/_config` shadow tables.
   - Row counts: `messages_fts=34243`, `messages_fts_trigram=34243`.

5. FTS5 self-test: `INSERT INTO <fts>(<fts>) VALUES('integrity-check')` per
   table on a write connection. (Run to completion to determine OK vs FAILED.)

## Correct FTS5 integrity check — why

`PRAGMA integrity_check` validates the B-tree and shadow tables but does NOT
walk each FTS5 index for token/index consistency. The canonical FTS5 check is
the special `integrity-check` command inserted *into* the virtual table, and it
requires a write-capable connection because it records results into the shadow
tables.

## Process-tree note

`ps aux | grep hermes` shows many lines; the gateway is the argv containing
`hermes gateway`, plus its `mcp_stdio_watchdog.py` children. `hermes dashboard`
parents are a different service. Don't conflate them.

## Resolution path

For THIS (per-session FTS-lag) case: rebuild the affected FTS index(es)
(drop + recreate from the messages content table) — a writable-DB mutation,
so **delegate to OpenCode**, then re-run the step-5 `integrity-check` to
verify. For the global-freeze / SQLITE_CANTOPEN case see SKILL.md "Resolution
→ Cause A" (fix the temp dir, restart the gateway; never rebuild indexes).
