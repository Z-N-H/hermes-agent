# ntfy blocked by the `nono` proxy allowlist (observed 2026-08-25)

A distinct ntfy failure from 40301 auth: the host is blocked, not the credentials.

## Symptom

`pantheon notify send` exits 1 and NEVER reaches ntfy:

```
ntfy POST to https://ntfy.sh failed: URLError(OSError('Tunnel connection failed: 403 Forbidden: host ntfy.sh:443 is not in the allowlist')); dropped notification: 'Pantheon'
✗ ntfy delivery failed — see log output above
```

`pantheon notify queue` shows the failures queued for retry with the tunnel reason:

```
2 undelivered notification(s) (/mnt/z/pantheon/.ntfy-deadletter.jsonl)
  ... queued <ts> · attempts 1 · ntfy POST to https://ntfy.sh failed: URLError(OSError('Tunnel connection failed:
  Retry with: pantheon notify retry
```

## Root cause

This host routes ALL outbound HTTPS through an allowlist proxy:

```
https_proxy=http://nono:572df2...@127.0.0.1:44935
HTTP_PROXY / HTTPS_PROXY / http_proxy / https_proxy all set
no_proxy=localhost,127.0.0.1
```

`nono` is a filtering/allowlist proxy. `ntfy.sh:443` is NOT on its allowlist, so the
CONNECT tunnel is refused with 403 Forbidden. The token resolution (gcloud → GSM → ntfy)
is irrelevant here and works fine; the request never leaves the proxy.

## Why you cannot bypass the proxy

Unsetting the proxy env vars and curling directly fails too (connection refused / no route):

```bash
HTTPS_PROXY= http_proxy= curl -s -m 8 -o /dev/null -w "%{http_code}\n" https://ntfy.sh/znh-pantheon
# => 000
```

The box has no direct egress to ntfy.sh; only the allowlist can permit it.

## Recovery (manual, user — not self-healing)

1. Add `ntfy.sh` (port 443) to the `nono` proxy allowlist, OR configure an allowed
   internal/self-hosted ntfy relay and point `pantheon notify config --server ...` at it.
2. Re-send the queued alerts: `pantheon notify retry`.
3. Confirm with `pantheon notify queue` reporting 0 undelivered, or a live
   `pantheon notify send "test"` returning exit 0 + `✓ Pushed to ntfy`.

## Distinguishing from 40301 auth failure

| Symptom | Meaning |
|---|---|
| `{"code":40301,"http":403,"error":"forbidden"}` JSON body | private-topic **auth** — anonymous publish |
| `URLError(OSError('Tunnel connection failed: 403 Forbidden: host ntfy.sh:443 is not in the allowlist'))` | **network** — proxy allowlist blocks the host |

A cron failure-alert path that depends on ntfy may deliver nothing if this block is
present; a failing alerting channel should be surfaced in the run report rather than
silently treated as success.
