---
name: hermes-session-storage-diagnosis
description: "Use when Hermes can't write session storage (state.db / SQLite write failures)."
version: 1.1.0
platforms: [linux]
metadata:
  hermes:
    tags: [hermes, gateway, state.db, sqlite, fts5, session, persistence, troubleshooting, ops]
---

# Hermes Session Storage Diagnosis

Umbrella for diagnosing Hermes **session-persistence failures**. The gateway
aborts a turn and tells the user session storage couldn't be written because
the transcript write to disk failed and would have been lost on restart.

## Trigger

Load this when any of these appear:
- User reports: `:warning: No reply: the turn was stopped because session
  storage could not be written (the transcript would have been lost on restart).
  Check disk space / permissions for the state DB...`
- Gateway log (`~/.hermes/logs/gateway.log`) contains:
  `Persisted transcript lagged live cached history ... (disk=N, memory=M);
  preserving live conversation context (possible FTS write corruption)`
- A Hermes turn silently produces no reply.

## The one key insight

**Classify before you conclude — there are two distinct causes with the same
user-visible symptom, and this runbook's earlier version memorably guessed the
wrong one.** Check BOTH before rebuilding anything:

### Cause A — sandbox-denied SQLite temp dir (SQLITE_CANTOPEN) — CHECK FIRST

Tells:
- The error suffix `[SQLITE_CANTOPEN]`, or `unable to open database file` in
  gateway logs.
- **`max(messages.timestamp)` frozen across ALL sessions at once** — cron and
  interactive alike — while the gateway process is alive and serving turns.
  (Per-session FTS lag freezes ONE session; an environment failure freezes
  the whole store.)
- Anything claiming "another Hermes process held the write lock … the
  database itself is healthy" is the retired b956845312 misclassification —
  do not believe a word past `database is locked`.

Mechanism (proven 2026-08-24): `pantheon-hermes-gateway.service` runs under
`nono --profile hermes`, which denies `/var/tmp`. SQLite picks its temp dir
with `access(2)` — which reports `/var/tmp` writable even when Landlock
denies open(2) — and with no `SQLITE_TMPDIR`/`TMPDIR` set falls through to
`/var/tmp` permanently. From the first FTS5 segment merge onward, EVERY
write needs a temp file → every write fails, permanently.

```bash
# Verify from inside the gateway's own sandbox policy:
nono why --profile hermes --path /var/tmp --op readwrite   # DENIED = cause A
sqlite3 file:~/.hermes/state.db?mode=ro "SELECT MAX(timestamp) FROM messages"
```

### Cause B — FTS5 index corruption / per-session index lag

Tells: `lagged live cached history (disk=N, memory=M)` for ONE session while
other sessions keep writing; `max(messages.timestamp)` keeps advancing
globally; FTS `integrity-check` (step 6) fails on a specific index.

The telltale gateway-log line shows the divergence:
```
WARNING gateway.run: Persisted transcript lagged live cached history for session
<session_id> (disk=25, memory=28); preserving live conversation context
(possible FTS write corruption)
```
`memory` climbing while `disk` stays frozen over ~30s = that session's FTS write
is stalled → triggers the user-visible warning.

## Diagnostic sequence (run in order)

1. **Disk space** (rule out in 2 seconds, then move on):
   ```bash
   df -h /mnt/z /home
   ```
   Skip `df -i` — on overlayfs it reads `0/0/0` and is a dead end. Use only the
   block-device `df -h` % number.

2. **Ownership vs the running processes** (permissions are a red herring but cheap):
   ```bash
   ls -la /mnt/z/pantheon/.hermes/state.db
   ps aux | grep -E "hermes.*gateway|hermes.*run" | grep -v grep
   id
   test -w /mnt/z/pantheon/.hermes/state.db && echo WRITABLE || echo NOT-writable
   ```
   Healthy here: DB owner uid (1000) matches gateway process uid (1000), write
   test passes.

3. **SQLite health** (read-only; `sqlite3` CLI is often not installed → Python):
   ```bash
   python3 -c "
   import sqlite3
   con = sqlite3.connect('file:/mnt/z/pantheon/.hermes/state.db?mode=ro', uri=True)
   print('integrity_check:', con.execute('PRAGMA integrity_check').fetchone()[0])
   print('journal_mode:', con.execute('PRAGMA journal_mode').fetchone()[0])
   print('busy_timeout:', con.execute('PRAGMA busy_timeout').fetchone()[0])
   con.close()"
   ```
   Healthy here: `integrity_check=ok`, `journal_mode=wal`, `busy_timeout=5000`.
   **A plain `PRAGMA integrity_check` does NOT validate the FTS index** — see step 5.

4. **Is the freeze GLOBAL or per-session?** (the cause-A vs cause-B fork):
   ```bash
   python3 -c "
   import sqlite3, time
   con = sqlite3.connect('file:/mnt/z/pantheon/.hermes/state.db?mode=ro', uri=True)
   ts = con.execute('SELECT MAX(timestamp) FROM messages').fetchone()[0]
   print('newest message age (s):', time.time() - ts)
   con.close()"
   ```
   Frozen for many minutes while the gateway is alive → cause A (temp dir /
   environment), NOT FTS. Also check `nono why --profile hermes --path
   /var/tmp --op readwrite`; note `os.access`/`test -w` LIE under Landlock —
   only a real `open(O_CREAT)` probe is authoritative:
   ```bash
   python3 -c "
   import os
   try:
       fd = os.open('/var/tmp/.probe', os.O_CREAT|os.O_EXCL|os.O_WRONLY)
       os.close(fd); os.unlink('/var/tmp/.probe'); print('real open OK')
   except OSError as e: print('real open FAILED:', e)"
   ```
   (run it inside the gateway's sandbox flags to reproduce the gateway's view).

5. **Inventory the FTS tables** (two of them exist):
   ```bash
   python3 -c "
   import sqlite3
   con = sqlite3.connect('file:/mnt/z/pantheon/.hermes/state.db?mode=ro', uri=True)
   for name,_ in con.execute(\"SELECT name,sql FROM sqlite_master WHERE type='table' AND name LIKE '%fts%'\").fetchall():
       print(name)
   con.close()"
   ```
   Expect `messages_fts` and `messages_fts_trigram` (each FTS5 virtual table +
   `_data`, `_idx`, `_content`, `_docsize`, `_config` shadow tables).

6. **FTS5 integrity-check** — the real test. Must run on a WRITE connection
   (the command writes its findings to shadow tables):
   ```bash
   python3 -c "
   import sqlite3
   con = sqlite3.connect('file:/mnt/z/pantheon/.hermes/state.db?mode=rw', uri=True)
   con.execute('PRAGMA busy_timeout=10000')
   for tbl in ['messages_fts','messages_fts_trigram']:
       try:
           con.execute(f\"INSERT INTO {tbl}({tbl}) VALUES('integrity-check')\")
           print(tbl, 'INTEGRITY OK')
       except Exception as e:
           print(tbl, 'FAILED ->', e)
   con.close()"
   ```
   Also measure the index lag: compare `max(id)` in each `_content` table.

7. **Read the gateway log for the exact lag warning**:
   ```bash
   grep -iE "state\.db|sqlite|ENOSPC|no space|storage|locked|lagged live|could not be written|FTS" \
     /mnt/z/pantheon/.hermes/logs/gateway.log | tail -40
   ```
   The `Session storage: <path>` INFO lines show the DB path; the
   `lagged live cached history (disk=N, memory=M)` WARNING lines show divergence.

## Pitfalls

- **Don't stop at "disk is fine" — and don't jump to "it's the FTS index".**
  The earlier version of this runbook said it was "almost always" FTS; the
  2026-08-24 incident proved that wrong (21 hours frozen, sandbox-denied temp
  dir). Classify global-vs-per-session first (step 4).
- **`os.access` / `test -w` / `stat` LIE under Landlock** (nono's enforcement
  mechanism): they answer from DAC bits while open(2) is what the policy
  restricts. Only a real `open(O_CREAT)` probe is authoritative. This also
  applies to any writability preflight you write or audit.
- **Retry-bucket messages can misclassify.** b956845312 folded
  SQLITE_CANTOPEN into the lock-retry bucket and reported lock contention
  plus "the database itself is healthy". Read the `[SQLITE_*]` suffix; it
  is the only truthful part of such messages.
- **`df -i` is useless on overlayfs** — it reports 0/0/0. Don't chase it.
- **FTS integrity-check needs a write connection** even to verify read-only
  data; the SQLite CLI isn't installed, so use Python.
- **Session IDs embed the channel.** A `slack:dm` session is a Slack DM; a
  `disk vs memory` row-count comparison isolates which session is lagging.
- **Decode the process tree.** Multiple `hermes` lines appear in `ps`; the
  gateway is the process whose argv includes `gateway` (plus its
  `mcp_stdio_watchdog` children). `hermes dashboard` parent lines are not it.

## Resolution (delegate the code work)

**Cause A (sandbox temp dir / SQLITE_CANTOPEN):** do NOT rebuild FTS indexes
— they are fine. Fix the temp dir instead: the launcher sets
`SQLITE_TMPDIR`/`TMPDIR` at exec time (Pantheon grant: `~/.hermes/tmp`) AND
`hermes_state.py` pins `PRAGMA temp_store_directory` on every connection.
Then restart the gateway with
`systemctl --user restart pantheon-hermes-gateway` (never
`hermes gateway restart` — it has previously orphaned a duplicate holding
the singleton lock). Verify by writing a probe message into a test session
and re-checking `max(messages.timestamp)`.

**Cause B (FTS index lag / corruption):** rebuild the affected FTS index
(drop + recreate `messages_fts` / `messages_fts_trigram` from the messages
content table). This is a writable-DB operation — **delegate it to OpenCode**
(orchestration boundary; never write DB mutations by hand). Verify afterwards
with the step-6 FTS integrity-check.

## References

- `references/hermes-session-storage-fts-diagnosis.md` — full command walkthrough
  with the actual healthy-state output captured from the Pantheon box.
