# Cron Job Verification Walkthrough

**Context:** A user asked "is the librarian cron job live and running?" after it was created and registered. The following diagnostic steps confirmed the job was live.

## The Problem

`hermes cron list` showed the job was registered with a future `Next run` timestamp, but:
- The `ticker_heartbeat` and `ticker_last_success` files under `.hermes/cron/` were over a month old
- Gateway logs only showed "Cron ticker started" during boot — no per-tick logging
- No session-level output had been seen yet (first run hadn't occurred)

## Step-by-Step Diagnosis

### 1. Check Registration + Schedule

```bash
hermes cron list | grep -A8 vault-librarian
```

Output:
```
Name:      vault-librarian
Schedule:  every 720m
Repeat:    ∞
Next run:  2026-07-30T10:24:30.219225+01:00
```

**Signal:** Job is registered with a valid future time. No `last_run_at` means it hasn't fired yet.

### 2. Check Gateway Health

```bash
hermes cron status
```

Output:
```
✓ Gateway is running — cron jobs will fire automatically
  PID: 1675733

  1 active job(s)
  Next run: 2026-07-30T10:24:30.219225+01:00
```

**Signal:** Gateway is up. PID matches running process.

### 3. Check Ticker Heartbeat Files

```bash
cat /mnt/z/pantheon/.hermes/cron/ticker_heartbeat
cat /mnt/z/pantheon/.hermes/cron/ticker_last_success
date +%s
```

Output:
```
1782307631.6019785
1782307631.6155076
1785402004
```

**Diagnosis:** These files are 35+ days old (June vs current July timestamp). **They are from a previous cron implementation — IGNORE them.** The current gateway tracks ticks in-memory and doesn't write to these files. Relying on them yields a false "ticker is dead" signal.

### 4. Check Gateway Logs

```bash
tail -100 /mnt/z/pantheon/.hermes/logs/gateway.log | grep -i "cron\|tick\|job"
```

Output:
```
2026-07-29 18:21:56,918 INFO gateway.run: Cron ticker started (interval=60s)
```

**Signal:** The ticker started at Gateway boot and has been running since. No subsequent "stopped" entry means it's still active.

Full tail for context:
```
2026-07-29 18:21:50,049 INFO gateway.run: Cron ticker stopped        # Previous instance
2026-07-29 18:21:56,918 INFO gateway.run: Cron ticker started (interval=60s)  # Current instance
```

### 5. Manually Trigger the Job

```bash
hermes cron run vault-librarian
```

Output:
```
Triggered job: vault-librarian (vault-librarian)
  Next run: 2026-07-30T10:00:12.454467+01:00
  It will run on the next scheduler tick.
```

**Note:** This queues the job but doesn't execute it immediately. It waits for the next 60s tick cycle.

### 6. Force a Scheduler Tick (May Fail)

```bash
hermes cron tick
```

**Known behaviour:** This command can time out (exit code 124 after 30+ seconds). When it does, **don't retry it** — just wait for the automatic tick cycle.

### 7. Wait and Re-check

```bash
sleep 65   # 60s tick interval + 5s buffer
hermes cron list
```

Output:
```
Name:      vault-librarian
Schedule:  every 720m
Repeat:    ∞
Next run:  2026-07-30T22:00:18.287392+01:00    # ← Moved forward 12 hours!
```

**Confirmation:** The `Next run` timestamp advanced by the job's full schedule interval (720m = 12h). This is definitive proof the job actually ran on the tick cycle.

## Summary Diagnostic Flow

```bash
# 1. Check registration
hermes cron list | grep -A5 <job-name>

# 2. Check gateway
hermes cron status

# 3. Check gateway logs for ticker health
tail -50 <HERMES_HOME>/logs/gateway.log | grep -i "cron\|tick"

# 4. Trigger manually
hermes cron run <job-name>

# 5. Wait a tick cycle + verify Next run moved
sleep 65
hermes cron list | grep -A5 <job-name>
```

## Key Lessons

1. **Heartbeat files are unreliable** — the old `ticker_heartbeat`/`ticker_last_success` files are not updated by the current gateway. Never use them to judge ticker health.
2. **`Next run` movement is truth** — if it advances by the schedule interval after a manual trigger + wait cycle, the job executed.
3. **`hermes cron tick` may hang** — timeout-after-30s is a known quirk. The automatic 60s tick always works, so just wait.
4. **Gateway log inspection** — search for "Cron ticker started" as the definitive alive signal. No "stopped" after it = still ticking.
