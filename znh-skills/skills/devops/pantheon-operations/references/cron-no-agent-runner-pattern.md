# `no_agent=true` Runner Pattern — Inbox Scanner Example

## Background

The inbox-scanner cron job needed to send Slack Block Kit messages, but the Hermes cron framework injects a system-level instruction: **"do NOT use send_message or try to deliver the output yourself — your final response will be auto-delivered."** This instruction cannot be overridden at the prompt level — it's in the system prompt assembly.

The workaround: use `no_agent=true` so the cron scheduler runs a Python script (not an LLM session). The script then calls `hermes chat -q` directly, which gives the model full tool access including `send_message` with `blocks`.

## The Runner Script

Path: `.hermes/scripts/inbox_scanner_runner.py`

### Structure

```
1. Scan inbox notes' triage: frontmatter — classify into buckets
2. If nothing needs attention → exit 0 silently (empty stdout = no delivery)
3. Otherwise, build a combined query string:
   - Inbox state as context (untriaged, failed, done, parked, discarded)
   - Full processing prompt (vault-triage skill, Block Kit templates)
4. Call: hermes chat -q via subprocess.Popen (fire-and-forget)
5. Exit 0 immediately — hermes runs in background
```

### Key Design Decisions

1. **Fire-and-forget (`subprocess.Popen`)** — The cron scheduler kills scripts that run longer than 120s, and a `hermes chat -q` session processing multiple notes can take several minutes. Using `subprocess.run()` with a 600s timeout worked for hermes itself but the surrounding cron job was killed first. The fix: use `subprocess.Popen()` and return immediately. The hermes process runs in the background, processes notes, and handles Slack delivery itself.

   ```python
   # WRONG — blocks and gets killed by cron scheduler at 120s
   subprocess.run([HERMES, "chat", "-q", prompt, ...], timeout=600)

   # RIGHT — returns immediately, hermes runs in background
   subprocess.Popen(
       [HERMES, "chat", "-q", prompt, ...],
       stdin=subprocess.DEVNULL,
       stdout=subprocess.DEVNULL,
       stderr=subprocess.DEVNULL,
   )
   ```

2. **`subprocess.DEVNULL` on stdin, stdout, stderr** — The `hermes chat -q` session uses `send_message` for Slack delivery. With `no_agent=true`, the scheduler also delivers stdout verbatim. Suppressing stdout prevents the message from being delivered twice (once via `send_message`, once via stdout forwarding). Stderr to DEVNULL prevents stderr from hanging the Popen process. Stdin to DEVNULL prevents SIGTTIN if the process tries to read from stdin.

3. **Silent exit on "nothing to do"** — When the scanner finds no new files, the script exits 0 with no stdout. With `no_agent=true`, empty stdout means nothing is delivered — no noisy "inbox clear" every 30 minutes.

### Exit Code Semantics

With `no_agent=true`, non-empty stdout IS delivered to the user:
- **Exit 0 + empty stdout** → Silent — nothing is delivered
- **Exit 0 + non-empty stdout** → Content is delivered verbatim
- **Exit non-zero** → Treated as script failure, cron shows "error" status

For the runner:
- Empty inbox or nothing needing LLM → exit 0, empty stdout (silent)
- Work found and hermes launched → exit 0, empty stdout (hermes handles Slack itself)
- Hermes not found → print error to stdout, exit 0 (so user sees the error via cron delivery)
