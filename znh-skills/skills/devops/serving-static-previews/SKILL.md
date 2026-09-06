---
name: serving-static-previews
description: Use when serving static files over the tailnet via HTTPS.
---

# Serving Static Previews Over the Tailnet

## When to Use

- Wireframe / HTML / PDF / report previews the user wants to open on another tailnet device.
- Working OUTSIDE an active pantheon task worktree (completed/archived tasks, scratch/, arbitrary directories).
- A dev/preview server served over the tailnet where requests 403 on the tailnet host (`preview.allowedHosts`), or a built site renders unstyled at a subpath (root-absolute asset URLs) — see the Astro sections below.

If inside an ACTIVE pantheon task, prefer the native flow instead: put files in `./tailscale/` and run `pantheon serve` (see `pantheon-serve-static` skill) — it allocates the port, starts the server, mounts tailscale, and auto-cleans on `pantheon task finish`.

## Steps

### 1. Start a static server (background process)

```bash
uvx python -m http.server 8899 --bind 127.0.0.1 --directory /abs/path/to/dir
```

- Python MUST run via `uv`/`uvx` (project rule — never bare `python3 -m http.server`).
- Serve the DIRECTORY containing the files, not a single file — relative assets (`wireframe.css`, images) only resolve when the whole dir is the web root.
- Launch with terminal(background=true); give it a moment, then verify locally.

PITFALL: `bun serve ./dir --port 8899` does NOT work on this box — the installed bun has no `serve` subcommand and exits with `error: Script not found "serve"`. Don't reach for bun for static serving.

### 2. Verify locally before touching tailscale

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8899/file.html
```

Expect 200. `000` / "Failed to connect" = server not up — check the background process log.

### 3. Mount on the tailnet

The root path is frequently already taken by other mounts (check `tailscale serve status` first), so mount at a subpath:

```bash
tailscale serve --bg --set-path /my-name http://127.0.0.1:8899
```

If the root path is genuinely free and wanted: `tailscale serve --bg http://127.0.0.1:8899`.

Confirm with `tailscale serve status`, then the URL is:
`https://<host>.<tailnet>.ts.net/my-name/file.html`
(relative asset links work because the mount proxies the whole directory under the subpath).

### 4. Verify through the tailnet URL — not just localhost

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://bazzite.centaur-perch.ts.net/my-name/file.html
curl -s -o /dev/null -w "%{http_code}\n" https://bazzite.centaur-perch.ts.net/my-name/style.css
```

Check both the page and its assets — proxy/subpath config errors only show up on the tailnet URL.

### 5. Cleanup

```bash
tailscale serve --set-path /my-name off   # remove one mount
tailscale serve --https=443 off            # disable all serve config
# then kill the background http.server process
```

## Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| 502 Bad Gateway / blank page | Local server not running or died | curl localhost first; check the bg process log; restart |
| Mount fails or `--set-path` rejects the name | Root path already proxied by another service | Use `--set-path` (subpath), never fight for root |
| 200 locally but 404 via tailnet | Mounted a single file instead of its directory | Serve the directory so subpath-relative assets resolve |
| Stale content served | Server restarted on a different port | `tailscale serve status`, re-mount the new port |
| 403 "Blocked request. This host ... is not allowed" via tailnet (200 via localhost) | Dev/preview server (Astro, Vite) enforces a `preview.allowedHosts` allowlist; tailnet Host header not allowed | Add the tailnet hostname to `preview.allowedHosts` (Astro: `vite.config.js`/`astro.config.mjs`) or set `allowedHosts: true`, then restart the preview server — see below |
| Site renders *completely unstyled* under a subpath (default serif, block layout, no cards/colours; HTML present but raw) | Build emitted root-absolute asset URLs (`/assets/...`) which resolve to the tailnet ROOT (often a different service) instead of `/subpath/assets/` | Make the framework build subpath-aware (`base` in `astro.config.mjs`/`vite.config.js`, ideally env/flag-driven so the root deployment still works), rebuild, re-serve; check both the stylesheet `<link>` href and the CSS's own `@font-face url(...)`. Full diagnosis ladder + knock-on checks (API base, sitemap, OG tags): `references/unstyled-site-at-subpath.md` |

## Astro / Vite preview servers reject the tailnet host (403)

A plain `python -m http.server` serves any Host value, so mounting it on the
tailnet just works. But **Astro/Vite's preview/dev server enforces a host
allowlist** — by default only `localhost`/`127.0.0.1`. Tailscale forwards the
tailnet hostname (e.g. `bazzite.centaur-perch.ts.net`) as the Host header, so
proxied requests get:

```
HTTP/2 403  Blocked request. This host ("bazzite.centaur-perch.ts.net") is not allowed.
             To allow this host, add "bazzite.centaur-perch.ts.net" to
             `preview.allowedHosts` in vite.config.js.
```

**Diagnosis that distinguishes this from a mount/proxy problem:** curl the
page via plain localhost (200) vs. the tailnet URL (403), then confirm it's
the app's own host check (not the tailscale proxy) by forging the Host header
locally with no tailscale involved:
`curl -H "Host: bazzite.centaur-perch.ts.net" http://localhost:PORT/` → 403.
403. That also explains why the tailnet mount *is* correctly configured and the
app is up, yet the URL 403s.

The Astro dev/preview server binds IPv6 `[::1]` by default — verify with `localhost`
(e.g. `curl http://localhost:4321/` = 200) rather than `127.0.0.1` (which returns
`000` / connection refused), or you'll wrongly conclude the server is down.


**Fix:** add the tailnet hostname (or open it up) to the preview server's
allowed-hosts config — Astro: `preview.allowedHosts: ["bazzite.centaur-perch.ts.net"]`
in `astro.config.mjs` (or `allowedHosts: true` in a `vite.config.js`); then
restart the preview server and re-verify through the tailnet URL. This is a
code/config edit on the app, so route it through the normal code-delegation
path — but note it's also the exact same 403 you got from the dev server
before any tailscale work, so it's a dev-server config task, not a serving
task.


## `astro preview` can't serve a base-built site — use a clean-URL static server

For a site built WITH a non-root `base` (needed for subpath mounts), `astro preview`
**re-mounts everything under the base path** and 404s the prefix-stripped
requests the browser sends after the first load (internal nav, page assets).
It cannot serve a base-built `dist/` cleanly. Verified 2026-08-08 on the
UsefulUsability site mounted at `/usefulusability`.

**Fix that landed:** a tiny **Bun/Node static server** that maps clean URLs to
files **without a redirect**, so the browser keeps its prefix: an
`http.createServer` that reads the pathname, appends `/index.html` when the
path is a directory, and serves from `dist/` — `/tools` → `dist/tools/index.html`
(no `Location` redirect). Run it on the preview port, point
`tailscale serve --set-path /subpath` at it, and leave the tailscale mount
untouched across rebuilds. Root-absolute (no base) sites can still use
`astro preview`; the clean-URL server is only needed once a base is involved.


## Root-relative JS-SPA apps (PocketBase admin, etc.) need a dedicated HTTPS PORT, not a subpath

Some apps — notably single-page web apps like the **PocketBase admin UI** (`/_/`),
or any SPA that hard-codes root-absolute asset/API paths (`/js/...`, `/api/...`,
`/css/...`) — **cannot be mounted at a tailnet subpath** without breaking. If you
mount PocketBase at `--set-path /pb`, the browser requests `/js/admin.js` and
`/api/...` from the tailnet ROOT (which proxies a *different* service, e.g. the
:9999 mount), so the admin page returns HTML but is unstyled and its XHRs hit the
wrong service. Verified 2026-08-08 on UsefulUsability.

**Correct pattern — a dedicated root HTTPS port,** exactly like the `:42078`
mount already used for an OAuth callback:

```bash
# pick a free port, then mount root on it
tailscale serve --bg --https=48090 http://127.0.0.1:8090
# -> https://<host>.<tailnet>.ts.net:48090/   (proxies root -> 127.0.0.1:8090)
```

The root proxy on the *dedicated port* preserves the SPA's root-relative paths
(the only mount that keeps them intact), and because it's on its own port it
doesn't collide with the existing `:9999` root mount on the main hostname.

**Diagnosis order** (rule out the usual suspects first):
1. `curl http://127.0.0.1:8090/api/health` → 200 (service is up).
2. Check `tailscale serve status` — confirm the root (`/`) is already taken by
   another mount (that's WHY a subpath would collide).
3. Test the admin SPA through the dedicated-port URL: `curl -o /dev/null -w "%{http_code}" https://<host>:48090/_/` (expect 200) AND confirm an asset resolves
   (`/api/health` returns JSON, page `<title>` is "PocketBase") — a subpath mount
   would return HTML but the asset/API probes would hit the wrong root service.

A dedicated HTTPS port is also reachable tailnet-only (not funneled), matching
the subpath-mount security posture. Prefer it any time you must expose an SPA
that owns root-relative URLs and the hostname root is already proxied.

## Overlap Note

The Pantheon-bundled skills `tailscale-serve-localhost` and `pantheon-serve-static` cover this territory for active pantheon tasks; this skill is the general/out-of-task variant (arbitrary directories, subpath mounts, uv-managed server).

## Reference files

- `references/unstyled-site-at-subpath.md` — step-by-step diagnosis of a framework site rendering unstyled under a subpath (root-absolute asset URLs) and the base-path fix, including the `preview.allowedHosts` 403 and knock-on checks.
