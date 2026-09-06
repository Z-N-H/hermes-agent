# Pantheon ntfy Wiring — Resolution Chain, Verification, Misdiagnosis

Session detail from 2026-08-04 (notification system setup + verification).

## Topic and auth status

- Topic: `https://ntfy.sh/znh-pantheon` — **private**, publishing requires an access token.
- Anonymous publish returns:
  ```
  HTTP 403  {"code":40301,"http":403,"error":"forbidden","link":"https://ntfy.sh/docs/publish/#authentication"}
  ```
  `40301` is the private-topic auth response (ntfy deliberately mimics 403 to avoid topic enumeration). It says nothing about the token's validity — only that the request carried no (or insufficient) credentials.

## Token resolution chain (what "the live path" means)

```
pantheon notify send "<msg>"
   └─ reads /mnt/z/pantheon/.hermes/secrets.toml      # manifest, not a value store
        └─ maps env var name NTFY_TOKEN → GSM secret name ntfy_token
        └─ calls: gcloud secrets versions access latest --secret=ntfy_token  (project znh-dev)
        └─ publishes POST to ntfy.sh/znh-pantheon with the resolved token
```

Fallback when env `NTFY_TOKEN` is unset (verified by code inspection):
`agent_context/scripts/ntfy.py` (via `secrets_manager.py`) reads `/mnt/z/pantheon/secrets.json`
and treats the value of its `NTFY_TOKEN` key as a **GSM secret name**, then resolves
the real token through gcloud.

## Why the value in secrets.json is NOT a placeholder

- `secrets.json` entry: `"NTFY_TOKEN": "ntfy_token"` — 10 chars starting `ntf...`.
- That string is the **name of the GSM secret**, i.e. a mapping entry. It is consumed
  as a name, not used as a token value.
- The "sync the real token in" fix would have been doubly harmful:
  - consumers resolve it as a name → `gcloud ... --secret=tk_...` → fails;
  - it writes a plaintext secret to disk, which `secrets_manager.py` exists to avoid.
- The "remove the key" fix would break the env-less fallback → unauthenticated pushes → 401.
- Correct action: **none**. The entry is correct as-is.

## Verification transcript

1. Anonymous `curl -d "..." ntfy.sh/znh-pantheon` → `403 forbidden` (scheme-less URL also fine, same result).
2. With token resolved from GSM (`gcloud secrets versions access latest --secret=ntfy_token`, project `znh-dev`, authed as zack@neary-hayes.co.uk), publish returned `HTTP 200`, event id delivered to topic.
3. `pantheon notify send "hello zack!"` → `✓ Pushed to ntfy: Pantheon` (exit 0) — end-to-end confirmed with zero manual credential handling.

## Misdiagnosis write-up (the meta-lesson)

The first OpenCode investigation read `secrets.json`'s `NTFY_TOKEN` value as a "10-char
placeholder, likely why publishing returns 40301". Both claims were wrong:
- the value is a GSM secret **name**, deliberately short;
- the 40301 was caused by the test publishing **anonymously** to a private topic.

A follow-up delegation was told to investigate consumers first and then, conditionally,
sync or remove — the conditional design is what saved the day: investigation found the
live fallback consumer (`ntfy.py`) and correctly took no action.

**Lesson for future sessions:** before flagging any secrets-file value as stale/placeholder
or proposing cleanup, (a) find its consumers, (b) understand whether the value is a name,
a path, or a literal secret, (c) check what an anonymous/unauthenticated call actually
returns for the service in question. When a "fix" could plausibly break a fallback,
prefer a conditional task that investigates before mutating.
