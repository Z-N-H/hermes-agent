# drvfs Permission Denied at Mount Root

## Session Context
- Date: 2026-06-23
- Drive: `Z:` mounted at `/mnt/z`
- WSL2, `networkingMode=Mirrored`
- Mount flags: `9p (rw,noatime,aname=drvfs;path=Z:\;uid=1000;gid=1000;symlinkroot=/mnt/,cache=5,access=client,msize=65536,trans=fd,rfd=6,wfd=6)`

## Symptom
```bash
$ ls /mnt/z/
ls: cannot open directory '/mnt/z/': Permission denied
```

```bash
$ ls -la /mnt/z/pantheon/.. 
ls: cannot open directory '/mnt/z/pantheon/..': Permission denied
```

```bash
$ find /mnt/z -mindepth 1 -maxdepth 1
# (empty — no results, no error)
```

```bash
$ sudo ls -la /mnt/z/
sudo: error while loading shared libraries: libsudo_util.so.0: cannot open shared object file: No such file or directory
```

## What Worked
Accessing subdirectories directly:
```bash
$ ls -la /mnt/z/pantheon/
# full listing succeeded
```

Probing known subdirectories:
```bash
$ for dir in pantheon projects temp tmp backups documents downloads desktop; do
    if [ -d "/mnt/z/$dir" ]; then echo "DIR: $dir"; fi
  done
# Output: DIR: pantheon
```

## Diagnosis
`stat /mnt/z/` showed `drwxrwxrwx` (777) and looked healthy, yet `ls` failed. This is a WSL drvfs `access=client` mapping quirk — the Windows-side ACL check on the drive root fails the Unix directory-read permission test, even though child directories are individually traversable.

## Takeaway
When `ls /mnt/<drive>` fails with Permission denied on a WSL drvfs mount:
1. Confirm the mount is active with `mount | grep /mnt/<drive>`.
2. Try listing a known subdirectory directly (e.g., `ls /mnt/z/pantheon/`).
3. If that works, the drive is mounted fine — just avoid listing the root from WSL.
4. Use Windows-side `dir` if you truly need the root contents.
5. Do not waste time with `sudo` or permission-fix attempts inside WSL — this is an interop mapping issue, not a Unix permission problem.

## Related: WSL Home Directory Permission Desync

A separate but equally blocking issue: the WSL home directory (`/home/<user>/`) can spontaneously lose read/execute permissions for the owner, becoming `drwxr-x---` or similar. This breaks **everything** under the home directory: shell configs, git configs, tool binaries (opencode, node, npm), and any project symlinks that traverse through `/home/<user>/`.

### Symptom
```bash
$ ls -la /home/znh/
ls: cannot open directory '/home/znh/': Permission denied

$ /home/znh/.bun/bin/opencode --version
/usr/bin/bash: /home/znh/.bun/bin/opencode: Permission denied
# Even though the binary itself is -rwxr-xr-x

$ sudo ls -la /home/znh/
sudo: error while loading shared libraries: libsudo_util.so.0: cannot open shared object file
```

### Root Cause
WSL2 permission state can desync from the underlying Windows filesystem after Windows updates, sleep/hibernate, or WSL service restarts. The directory appears with correct permissions in `stat` but the effective ACL has changed.

### Fix
**From a Windows shell (PowerShell or CMD):**
```powershell
wsl --shutdown
```
Then restart WSL (e.g., open a new WSL terminal or run `wsl`).

### Why inside-WSL fixes fail
- `sudo` is often broken in the same permission state (`libsudo_util.so.0` missing)
- `chmod 755 /home/znh` may report success but not actually fix the underlying desync
- `wsl -u root chmod 755 /home/znh` works for some users but fails for others depending on WSL version and configuration

### Prevention
There is no reliable prevention. This is a known WSL2 bug. The `wsl --shutdown` fix is the safest and most consistent recovery.

### Diagnostic Checklist
When ANY tool under `/home/<user>/` returns "Permission denied" despite existing and being executable:
1. `ls -la /home/<user>/` — if this fails, it's the home-dir desync
2. `stat /home/<user>/` — may still show `drwxr-xr-x` (misleading)
3. Check if the tool's parent directories are traversable: `ls -la /home/<user>/.bun/` — if this fails too, it's the parent dir, not the tool
4. Fix: `wsl --shutdown` from Windows, then restart