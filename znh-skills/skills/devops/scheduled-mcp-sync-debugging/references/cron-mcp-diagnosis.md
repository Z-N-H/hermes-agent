# Cron-vs-Interactive MCP Tool-Count Diagnosis (real session trace)

Session date: 2026-08-24. Pipeline: `granola-meeting-scanner` cron job pulling
Granola meetings into the Obsidian vault. Initial full-sync run reported "0
meetings fetched" while the interactive session had queried Granola moments
earlier. This file records the exact evidence trail so the drill is concrete.

## The trace

1. **Interactive search succeeded at session start:**
   `mcp__pantheon__search(query="granola")` → `6 of 376 tools`, granola_* tools listed.
2. **First cron run (11:30):** `mcp__pantheon__search("granola")` → `0 of 370 tools`; get_schema → `Tools not found`. Cron handily reported the blocker, fired ntfy, kept state absent.
3. **Interactive search ALSO went 0/370 mid-session** — confirmed the MCP dropped off the hub for everyone, not just the cron subprocess.
4. **`pantheon mcp list`** (terminal): granola present, `●` enabled, `✅ authenticated`, namespace `granola`, Code Mode global.
5. **`pantheon mcp health`** (terminal): `granola — healthy: token valid`. → token fine, contradicting the missing tools → hub serving issue, not auth.
6. **`call_tool('pantheon_status', {})`** via `mcp__pantheon__execute`: `mounted_mcps` STILL lists `granola`, but the tools are missing from search. → the hub's mounted view lies; don't trust it alone.
7. **Hub stderr** `/mnt/z/pantheon/.hermes/logs/mcp-stderr.log`, `grep -i granola`:
   - `Interactive browser auth is not available in the hub. Run: pantheon mcp auth granola`
   - `Failed to connect OAuth MCP 'granola': RuntimeError: Client failed to connect: [Errno -2] Name or service not known`
8. **Shell DNS** was fine: `getent hosts mcp.granola.ai` → 4 IPs; `python3 -c socket.gethostbyname` → 3.173.161.117. So resolution failed only inside the hub's sandboxed/headless network context.

## Conclusion

- The cron job was behaving **correctly per design** (state not advanced → next
  tick retries as clean full initial sync; ntfy fired; no partial filings).
- The fix is a hub-level re-registration (hub restart, or
  `pantheon mcp auth granola` + hub restart), an infrastructure action.

## Golden rules learned

- `pantheon mcp health` = OAuth token health, INDEPENDENT of what the hub
  serves. "valid" ≠ "serving tools".
- The tool-count gap (376 → 370 = 6) is the smoking gun that an MCP (granola =
  6 tools) is unserved — compare interactive vs cron counts.
- Don't "fix" this by editing the skill prompt, changing the cron schedule, or
  swapping cron models. The model was never the problem.
- The design-verified failure path (leave state absent + ntfy + don't advance)
  is the SAFETY net; preserve it.

## Who owns this recipe

Umbrella: `scheduled-mcp-sync-debugging`. Filing details live in
`granola-meeting-filing` (user-owned; recommend `hermes curator adopt
granola-meeting-filing` to bring it under curation).
