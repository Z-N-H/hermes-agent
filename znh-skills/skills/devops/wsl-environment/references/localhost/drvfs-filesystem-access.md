# WSL drvfs Filesystem Access Quirks

## Symptom
`ls /mnt/<drive>` or `ls /mnt/<drive>/Users/` returns **Permission denied**, yet specific subdirectories like `/mnt/z/pantheon/` are fully accessible.

## Root Cause
WSL `drvfs` mounts can enforce access controls at the root level that block directory enumeration while still allowing access to known paths beneath. This depends on the Windows drive's ACLs and how drvfs translates them.

## Workarounds

1. **Access subdirectories directly** — bypass the root listing:
   ```bash
   ls /mnt/z/pantheon/          # works even if /mnt/z/ fails
   ```

2. **Use `stat` to verify existence** without listing contents:
   ```bash
   stat /mnt/c/Users
   ```

3. **Avoid `find` on blocked roots** — `find /mnt/z -maxdepth 1` will return only `/mnt/z` itself and silently skip children.

## What Does NOT Help
- Repeatedly trying `ls`, `dir`, or `find` with different flags — the root ACL is the blocker
- `sudo` — may fail if the WSL instance lacks the library or if drvfs ACLs are enforced at the 9p protocol layer

## Session Reference
- 2026-06-23: `/mnt/z/` and `/mnt/c/` roots blocked, `/mnt/z/pantheon/` accessible
