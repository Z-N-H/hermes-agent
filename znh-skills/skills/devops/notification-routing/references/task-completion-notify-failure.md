# Task-Completion ntfy Failure — Diagnosis & Verification Recipe

Session detail from 2026-08-16 ("ntfy system isn't working from completed tasks").

## The failure mode (silent drop)

The "✓ Task Completed" ping is not a Hermes/cron feature — it is emitted by the pantheon
CLI's completion notifier (`pantheon task finish` → `agent_context/scripts/ntfy.py`, installed
as the `pantheon` uv tool). Token resolution chain in `ntfy.py`:

```
env NTFY_TOKEN
  → /mnt/z/pantheon/secrets.json NTFY_TOKEN key   (a NAME: value is "ntfy_token", not a literal)
  → gcloud secrets versions access latest --secret=ntfy_token  (project znh-dev)
```

The bug: when gcloud can't refresh auth non-interactively it errors
`Reauthentication failed. cannot prompt during non-interactive execution.`, ntfy.py falls
through and attempts an **unauthenticated** publish to private topic `znh-pantheon`,
gets `40301`, and **drops the notification silently**. The user only ever notices "no ping".

## Why interactive verification lies

`pantheon notify send` from a freshly-authed interactive shell exits 0 with
`✓ Pushed to ntfy: <title>` while the completion path (which runs inside OpenCode's
non-interactive Bash, whose env descends from the Hermes gateway systemd user unit)
still drops. So a green interactive send proves nothing about completion pings.

## Diagnosis steps that worked

1. Read `~/.hermes/process-completions.jsonl` (append-only log of opencode-run completions
   with exit_code + full captured output). It is written by Hermes for background terminal
   runs with `notify_on_complete`.
2. Grep recent entries for: `dropped notification` / `40301` / `Reauthentication failed. cannot prompt`.
   Both appear verbatim in the captured output of the failing `pantheon task finish`.
3. Convert the `completed_at` epoch and compare `session_key` prefix dates — many log entries
   are replayed/old, so confirm you're looking at the relevant window.
4. Separately test the interactive path: `env | grep -i ntfy` (empty here) + `pantheon notify send`
   → succeeded. That contrast (interactive OK, completion fails) is the tell.

## Extras found during investigation

- A known-good **literal** token `tk_qbt90rlycxml4vmb6mtw7yyinc975` is embedded in
  `/mnt/z/pantheon/.claude/settings.local.json` line 181 (inside an allowlisted Bash command).
  Useful as a non-gcloud token source — the env var `NTFY_TOKEN` is preferred over secrets.json
  and gcloud by the resolver.
- The notifier only fires for **tracked** Pantheon tasks (`pantheon task finish`). Ad-hoc
  untracked `opencode run`s never call it, so they produce no ping at all. That's expected —
  not the bug.

## Verification recipe for any fix

1. `uv run pytest tests/test_ntfy.py` (and notifier tests) pass.
2. Reinstall/refresh the `pantheon` uv tool if the fix is in source, then
   `pantheon notify send "<msg>"` exits 0.
3. **Prove gcloud-independence**: run the same send with gcloud deliberately broken/expired
   (env/HOME override so the real gcloud isn't corrupted) and show the ping STILL succeeds via
   the injected persistent token.
4. Confirm the injection point actually propagates to the notifier's process context
   (OpenCode Bash ← Hermes gateway systemd unit) and that no plaintext token is committed to git.
