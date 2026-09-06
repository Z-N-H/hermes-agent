# Stale Hindsight UI — API restart doesn't fix empty-bank dashboard (2026-08-16)

## Symptom
User: "dashboard isn't showing any banks." Dashboard at
`https://bazzite.centaur-perch.ts.net/` loads (redirects to /dashboard,
"Hindsight Control Plane") but the bank selector is a **disabled "Loading..."**
button forever, and the help text reads "Select a memory bank from the dropdown
above to get started."

## What I got wrong first
I ran `systemctl --user restart pantheon-hindsight.service`, verified the API
was healthy, and reported "fixed." It wasn't — the dashboard still showed no
banks. The API was never the problem.

## Root cause
Hindsight is TWO independent service layers with different lifecycles:
- API on :8888 → owned by `pantheon-hindsight.service` (systemd).
- UI control plane on :9999 → detached `bunx hindsight-control-plane` launched
  by `pantheon-stack.sh`, NOT under systemd. This one had been up 12 days
  (PID 241072, `etime 12-01:24:57`) while the API underneath it had just been
  restarted. The stale Next.js UI client's bank-loading hook never fired, even
  though the backend data was intact and reachable.

## Diagnostic evidence (the useful sequence)
From the same box, separating "data gone" from "UI stale":

1. API healthy + data present:
   `curl -s http://127.0.0.1:8888/v1/default/banks`
   → `{"banks":[{"bank_id":"hermes","fact_count":6772,...},{"bank_id":"claude_code","fact_count":109,...}]}`
   (tenant is `default`; list full routes via `curl -s .../openapi.json`.)
2. Client-side, from the dashboard origin, `/api/banks` still returns both
   banks in ~11ms — proving the browser→UI-proxy→API path works and the defect
   is the UI component's client state, not routing or data.
3. `ps -eo pid,etime,cmd | grep hindsight-control-plane` → 12-day `etime`
   confirms the stale UI.

## Fix (worked)
```bash
pkill -f hindsight-control-plane
sleep 4
HOME=/home/znh /mnt/z/pantheon/vault/ZNH/scripts/pantheon-stack.sh start
```
`start` is idempotent/port-guarded: Phoenix (:6006), Hermes dashboard (:9119),
and the API (:8888) reported "already running" and were skipped; only the freed
:9999 UI relaunched (fresh PID), re-applying the proxy-header/locale patches in
`pantheon-stack.sh::_start_hindsight_ui` and re-registering tailscale paths.
After reload the dropdown listed both banks.

## Reusable rules
- The `pantheon-hindsight.service` systemd unit owns the API only. Restarting
  it never touches the UI control plane.
- "No banks / stuck Loading" on the dashboard is a UI-state symptom; check the
  API's `/v1/default/banks` before assuming data loss.
- If the UI process `etime` predates the last API restart, replace the UI
  process — don't chase backend config.
