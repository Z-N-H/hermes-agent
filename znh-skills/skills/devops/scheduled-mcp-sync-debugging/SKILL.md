---
name: scheduled-mcp-sync-debugging
description: Debug failing cron-to-MCP sync pipelines.
platforms: [linux]
environments: [hermes]
---

# Debugging & Building Scheduled MCP Sync Pipelines

Covers recurring work in this repo's vault/Pantheon stack: **cron jobs that
periodically pull external data (e.g. Granola meetings, Rize time, ClickUp) out
of an MCP through the Pantheon hub and file it into Obsidian / the vault.** Two
recurring lessons: (1) when to build these natively vs dispatch to OpenCode,
and (2) how to tell "the MCP isn't reachable" from "the pipeline logic is
wrong."

## Build the right way: native Hermes, not an OpenCode/systemd build

A scheduled pipeline whose **fetch step requires an MCP reachable only through
the Pantheon hub** needs an *agent turn* each tick (the Code-Mode
`search → get_schema → execute` pattern runs inside a Hermes/MCP session).
Consequently the canonical shape is:

- A **Hermes skill** (via `skill_manage`) encoding the fetch/classify/file/notify
  procedure, AND
- A **Hermes cron job** (via the `cronjob` tool) on a fixed cadence that loads
  that skill on each tick.

Check `docs/plans/*-design.md` first — if the finalized design specifies
"Hermes cron + skill (`hermes chat -q`)", follow it. Do NOT reinvent it as a
systemd timer + script, and do NOT dispatch it to OpenCode just because it
involves "code": OpenCode has separate MCP wiring and cannot drive the
Hermes-native hub tools for you. (The real touchstone: the filing skill here is
`granola-meeting-filing`; its design is `docs/plans/2026-08-19-granola-meeting-scanner-design.md`.)

## Design-verified failure path in the filing skill (keep intact)

When a sync runs but can't reach its MCP, the skill must:
- **NOT advance state** — leave the seen-IDs/state file absent so the next
  successful tick cleanly backfills (preserves one-time-initial-sync semantics).
- Fire an **ntfy alert** the first time (MCP unreachability / OAuth expiry
  doesn't self-heal).
- **Never advance past the missing fetch** — no partial/duplicate filings.

This behavior is a SAFETY property, not a bug — don't "fix" it by weakening the
skill. Full recipe: `references/cron-mcp-diagnosis.md`.

## Telling MCP unreachability from a logic/model bug (the key diagnostic)

Symptom: a cron run reports "0 meetings fetched" while your **interactive**
session can reach the same MCP fine. This is almost always a HUB
registration/connection problem, NOT a pipeline-logic, prompt, or model problem.
Methodical drill:

1. **Tool-count gap.** Compare `mcp__pantheon__search(query="<mcp>")` tool
   counts. Interactive `6 of 376` vs cron `0 of 370` → delta of exactly 6 =
   granola's tool count. When the delta equals the MCP's exposed tools, the MCP
   dropped off the hub for everyone.
2. **`pantheon mcp list`** — installed/enabled/authenticated (`●` + `✅`).
3. **`pantheon mcp health`** — OAuth token state is checked INDEPENDENTLY of
   the hub. "token valid / healthy" does NOT mean the tools are being served.
4. **`call_tool('pantheon_status', {})`** via `mcp__pantheon__execute` — the
   hub's own `mounted_mcps` view (note: it can claim "mounted" while its tools
   still missing from search results).
5. **Hub stderr log** `/mnt/z/pantheon/.hermes/logs/mcp-stderr.log`, `grep -i "<mcp>"`.
   Recognizable signatures:
   - `Interactive browser auth is not available in the hub. Run: pantheon mcp auth <name>`
     → headless hub can't do browser auth; needs a one-time interactive re-auth.
   - `Name or service not known` → DNS/egress from the hub's *own* sandboxed
     network context (differs from the shell: `getent hosts` / python resolve
     the domain fine, the hub process doesn't).

**Fix = re-register the MCP on the hub** (hub restart; `pantheon mcp auth
<name>` + hub restart if the token is actually stale). This is an infrastructure
action — NOT a skill-prompt, schedule, or model edit. Do not switch cron models
hoping a "better model" will brute-force the fetch; the model is not the problem.

**Pitfall (verified 2026-08-24): a bare hub restart does NOT repair a server
whose live connector fails.** `pantheon mcp server stop` + `start` re-mounts the
enabled set but the connector still cannot reach the MCP, so re-running
`mcp__pantheon__search` still returns 0 tools. The browser-auth step
(`pantheon mcp auth <name>`, requires an interactive foreground session) is the
mandatory part of the fix; the restart alone just changes the hub PID. In a
cron/agent context, correct behavior is still: don't advance state, ntfy-alert
the need for a human `pantheon mcp auth <name>`.

## Environment notes

- Trust the cron run's self-report; the agent usually handles the
  unreachable-MCP case correctly and reports an honest blocker. Verify via the
  drill above rather than assuming it got the tool list wrong.
- The monty `execute` sandbox: NO imports (json/os/re/sys), NO `print`; only
  `call_tool()` and builtins, end with `return <native object>`.

## Granola MCP API quirks (verified 2026-08-24)

Hit live while doing the one-time full backfill; new sessions will re-hit them.

- **`granola_get_meetings.meeting_ids` caps at 10 per call.** >10 is a hard
  validation error (`Array must contain at most 10 element(s)`). Batch any
  fetch of >10 meetings into ≤10-ID `get_meetings` calls.
- **`granola_list_meetings.time_range` is an ENUM**, only
  `this_week | last_week | last_30_days | custom`. Pass `custom` plus
  `custom_start` / `custom_end` (ISO `YYYY-MM-DD`) for a full-history pull.
- **The default/recent list window does NOT return full history.** A backfill
  relying on the implicit range only returned 7 of 20 meetings in one session.
  For any "pull everything" run (one-time initial sync, or a user asking to
  backfill all meetings into the vault), always list with an explicit wide custom
  span:
  ```python
  raw = await call_tool(
      "granola_list_meetings",
      {"time_range": "custom", "custom_start": "2025-08-24", "custom_end": "2026-08-24"},
  )
  return raw
  ```
  Then fetch summaries for the returned IDs in ≤10-ID `get_meetings` batches
  and file each (append each ID to the state file atomically with its note).

## File placement correction (user preference, 2026-08-24)

When the user asks for a write-up / findings / notes for **them** (to read, send
on, or keep), put it in the **Obsidian vault** (`/mnt/z/pantheon/vault/ZNH/`,
e.g. `Research/` or `Meetings/`), NOT in the Pantheon repo's `docs/plans/`.
The user corrected this directly: wrote a DNS-container-findings note to
`/mnt/z/pantheon/docs/plans/` and got "that's not even in the vault". Vault
notes to give the user carry frontmatter (`uid`, `type`, etc.) and live where
they sync to Obsidian; repo `docs/plans/` is for implementation/design docs.

