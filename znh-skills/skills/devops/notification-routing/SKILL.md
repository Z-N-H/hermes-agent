---
name: notification-routing
description: Send notifications via ntfy; Slack for conversation/action.
version: 1.0.0
platforms: [linux]
environments: [hermes]
metadata:
  hermes:
    tags: [notification, ntfy, slack, alerting, routing, preference]
---

# Notification Routing (ntfy primary, Slack reserved)

## The rule (user preference, 2026-08-04)

- **General notifications / status updates → ntfy** topic `https://ntfy.sh/znh-pantheon`.
- **Slack is reserved for genuine conversations or situations where an answer or action is needed from the user.** If the message does not need a human reply, decision, or action, it does not belong on Slack.

Apply this when: choosing a cron job `deliver` target, sending heartbeat/status/completion/inbox-summary pings, alerting on failures, or reporting background work. Only route to Slack when you are asking something or need a decision. When in doubt, default to ntfy.

## Sending to ntfy

Preferred path — the established Pantheon integration, no token wrangling:

```bash
pantheon notify send "<message>"
```

- Resolves credentials automatically: `.hermes/secrets.toml` (a manifest mapping env `NTFY_TOKEN` → Google Secrets Manager secret `ntfy_token`, project `znh-dev`), then publishes to topic `znh-pantheon`.
- Verified working 2026-08-04 (exit 0, `✓ Pushed to ntfy: <title>`).
- Check `pantheon notify --help` for title/options (observed default title: `Pantheon`).

Fallback chain (why you never need a raw token):
1. env `NTFY_TOKEN` if set
2. `.hermes/secrets.toml` manifest → `gcloud secrets versions access latest --secret=ntfy_token` (project `znh-dev`)
3. `agent_context/scripts/ntfy.py` falls back to `secrets.json`'s name mapping when env is unset

Raw curl only as last resort (token required):

```bash
curl -H "Authorization: Bearer $NTFY_TOKEN" -H "Title: <title>" -d "<message>" https://ntfy.sh/znh-pantheon
```

## Cron job deliver targets

- Background/status jobs (heartbeats, scans, watchers, summaries that do not need a decision) → ntfy. For a `no_agent=true` script-only job, have the script call `pantheon notify send` and keep `deliver: local` (CLI sessions have no live-delivery channel — a local cron job cannot push to ntfy on its own unless the script or agent does it).
- Only a job that explicitly asks the user a question or needs a decision should use Slack delivery.
- Recurring-user-preference note: each new job's prompt/script should embed the routing rule rather than assuming Slack.

## Pitfalls

1. **ntfy `40301 forbidden` = private topic needs auth.** Anonymous POST to a private topic returns `{"code":40301,"http":403,"error":"forbidden","link":"https://ntfy.sh/docs/publish/#authentication"}`. This is the private-topic auth response, NOT evidence of a bad credential and NOT a reason to publish the topic. Authenticate; expect HTTP 200 with a valid token.
2. **Do NOT "fix" the `NTFY_TOKEN` entry in `/mnt/z/pantheon/secrets.json`.** Its value (`ntfy_token`) is the GSM secret NAME — a name mapping, not a literal token — consumed as the env-less fallback by `ntfy.py`. Writing a real token into that key makes the resolver call `gcloud ... --secret=tk_...` and fail, and puts a plaintext secret on disk; deleting the key breaks the fallback (unauthenticated pushes → 401 when the env var is unset).
consumers find them -- or take no action if the entry is correct.
3. **Unicode variation-selector / emoji chars in the message body block the send command.** A body like `pantheon notify send "⚠️ Granola sync failed"` trips the Hermes security scanner (`tirith:variation_selector`); in a no-user cron run the terminal call lands in `pending_approval`/`approval_pending: true` and never executes. Keep ntfy (and other shell-sent) message bodies plain ASCII — no ⚠️✅→—. If a send comes back approval-blocked, resend with emoji stripped; exit 0 + `✓ Pushed to ntfy` confirms delivery.
4. **Task-completion pings have a silent-drop failure mode.** The "✓ Task Completed" ping fires from `pantheon task finish` via `agent_context/scripts/ntfy.py`. Its token chain is: env `NTFY_TOKEN` → `/mnt/z/pantheon/secrets.json` `NTFY_TOKEN` key (**a NAME**, value `ntfy_token`) → `gcloud secrets versions access latest --secret=ntfy_token`. If gcloud can't refresh auth non-interactively (the normal state inside OpenCode's Bash context, not just a one-off expiry), ntfy.py falls through and publishes **UNAUTHENTICATED** to the private topic → 40301 → **silently drops the ping** with no error surfaced to the user. Diagnose a missing completion ping via `~/.hermes/process-completions.jsonl`: grep for `dropped notification`, `40301`, or `Reauthentication failed. cannot prompt during non-interactive execution`.
5. **Interactive `pantheon notify send` success ≠ completion path works.** An end-to-end send from a freshly-authed interactive shell can exit 0 while the non-interactive completion context still drops. To verify any ntfy fix you MUST reproduce the non-interactive context (break/expire gcloud) and prove the ping still goes out via a non-gcloud token path — see `references/task-completion-notify-failure.md`.
6. **Only `pantheon task finish` pings — ad-hoc `opencode run`s never do.** The notifier is wired into tracked Pantheon-task completion only. Plain/untracked opencode runs don't invoke `pantheon task finish`, so they produce no ntfy at all. "No ping" for a non-tracked task is expected, not a bug; making every opencode-run completion ping is a separate, broader change.
7. **ntfy blocked by the `nono` proxy ALLOWLIST — distinct from the 40301 auth failure.** This box routes outbound HTTPS through `HTTPS_PROXY=http://nono:<token>@127.0.0.1:44935`, an allowlist-enforcing proxy. Unless `ntfy.sh` is on its allowlist, `pantheon notify send` fails with `URLError(OSError('Tunnel connection failed: 403 Forbidden: host ntfy.sh:443 is not in the allowlist'))` (exit 1, `✗ ntfy delivery failed`). Do NOT misread this as the 40301 private-topic auth error — the token is fine; the host is blocked. Diagnose via `pantheon notify queue`: undelivered entries show the tunnel reason, e.g. `2 undelivered notification(s) (/mnt/z/pantheon/.ntfy-deadletter.jsonl)`. Fix = add `ntfy.sh` to the proxy allowlist (or configure an allowed internal relay), then `pantheon notify retry`. Bypassing the proxy (`HTTPS_PROXY=` unset in a subshell) does NOT help — the box has no direct route, so curl returns `000`; the allowlist itself must permit the host. See `references/ntfy-proxy-allowlist-block.md`.

## References

- `references/ntfy-pantheon-wiring.md` — full token-resolution chain, 40301 semantics, verification transcript, and the misdiagnosis write-up.
- `references/task-completion-notify-failure.md` — silent-drop failure mode of the "✓ Task Completed" notifier, why interactive verification lies, diagnosis steps (`process-completions.jsonl`), and the gcloud-independence verification recipe.
