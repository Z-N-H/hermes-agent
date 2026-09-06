---
name: wsl-filesystem
description: Navigate and troubleshoot WSL2 filesystem quirks — drvfs permissions, case sensitivity, symlinks, and Windows path translation.
version: 1.0.0
---

# WSL2 Filesystem Quirks

## Trigger Conditions
- `ls`, `find`, or `stat` on a Windows-mounted drive (`/mnt/c`, `/mnt/z`, etc.) fails with `Permission denied`
- Unexpected case-sensitivity behavior when working across Windows and WSL boundaries
- Symlinks created in WSL behave differently when accessed from Windows (or vice versa)
- Path translation needed between Windows (`C:\Users\...`) and WSL (`/mnt/c/...`) formats

## Core Concepts

WSL2 mounts Windows drives via a 9p/drvfs filesystem. The mount options include `access=client`, meaning permission checks are delegated to the Windows side. This creates several non-obvious behaviors that differ from native Linux filesystems.

## drvfs Permission Quirks

### Symptom
`ls /mnt/z` returns `Permission denied` even though:
- The mount is active (`mount | grep /mnt/z` shows the drvfs entry)
- `stat /mnt/z` shows `drwxrwxrwx` and looks healthy
- Subdirectories like `/mnt/z/pantheon/` list perfectly fine

### Root Cause
WSL's `access=client` mode delegates permission checks to Windows. The Windows root of the drive may have ACLs or inheritance settings that prevent the Unix `r-x` check on the directory itself, even though individual subdirectories are accessible. This is a mapping mismatch, not an actual denial.

### Workaround
Instead of listing the drive root, access known subdirectories directly:
```bash
# Fails:
ls /mnt/z/

# Works:
ls /mnt/z/pantheon/
ls /mnt/z/projects/
```

If you need to discover what's on the drive root, use Windows-side tools:
```powershell
# From Windows PowerShell/CMD:
dir Z:\
```

Or, if you know approximate names, probe directly:
```bash
for dir in pantheon projects temp tmp backups documents downloads desktop; do
  if [ -d "/mnt/z/$dir" ]; then echo "DIR: $dir"; fi
done
```

### Avoid
- Do not assume the mount is broken just because the root lists as Permission denied.
- Do not loop on `ls /mnt/z` with `sudo` — WSL's `sudo` often lacks the necessary library path inside minimal containers, producing `libsudo_util.so.0: cannot open shared object file` instead of solving the permission issue.

## Case Sensitivity

Windows filesystems are case-preserving but case-insensitive. WSL's ext4 filesystem is case-sensitive. When a file or directory is created in WSL and then accessed from Windows (or vice versa), case mismatches can cause confusion.

### Rule of Thumb
- Always use the exact case that was used when the item was created.
- When in doubt, use `find` with `-iname` for case-insensitive search within WSL.

## Symlinks

Symlinks created in WSL may appear as `.lnk` files or plain files in Windows, depending on how they're created. Conversely, Windows shortcuts (`.lnk`) are not true symlinks and won't follow in WSL.

### Rule of Thumb
- Create symlinks in WSL with `ln -s` when both sides need to follow them.
- Avoid relying on Windows `.lnk` files from WSL scripts.

## Path Translation

### WSL → Windows
Use `wslpath`:
```bash
wslpath -w /mnt/z/pantheon
# Output: Z:\pantheon
```

### Windows → WSL
```bash
wslpath -u 'Z:\pantheon'
# Output: /mnt/z/pantheon
```

### In Scripts
Always use `wslpath` for cross-boundary path conversion rather than string replacement.

## Home Directory Permission Desync

A recurring WSL2 bug: `/home/<user>/` spontaneously becomes unreadable (`drwxr-x---` or similar) due to Windows/WSL interop permission mapping failures. This typically happens after Windows updates, sleep/hibernate, or WSL restarts.

### Symptom
```bash
$ ls -la /home/znh/
ls: cannot open directory '/home/znh/': Permission denied

$ git status --short
warning: unable to access '/home/znh/.gitconfig': Permission denied
fatal: unknown error occurred while reading the configuration files

$ whoami
whoami: cannot find name for user ID 1000
```

Any tool that touches the home directory fails: git, opencode (lives under `~/.bun/` or `~/.local/`), pytest (reads config from `~/.config/`), `sudo` (`libsudo_util.so.0: cannot open shared object file`), ssh, shell profiles, etc.

### Root Cause
WSL2's `drvfs` permission mapping desynchronizes the Unix user ID with the Windows SID. The home directory ACLs flip to deny read access for the WSL user. This is a Windows-side state issue, not a Linux permission problem.

### Fix (Proper)
Run `wsl --shutdown` from a **Windows** shell (PowerShell or CMD), then restart WSL:
```powershell
# In Windows PowerShell or CMD — NOT inside WSL
wsl --shutdown
# Then restart your WSL session
```

This forces WSL to re-initialize the permission mapping from scratch. Do NOT try `chmod`, `chown`, or `sudo` from inside WSL — `sudo` itself is broken in this state, and permission changes made from inside WSL are often ignored or reverted by Windows.

### Workarounds (When You Cannot Restart WSL)

**For git read-only operations:**
```bash
export HOME=/tmp
export GIT_CONFIG_GLOBAL=/dev/null
git -C /path/to/repo status --short
git -C /path/to/repo diff --stat
```

**For tools needing a writable home:**
```bash
mkdir -p /mnt/z/.tmp_home
export HOME=/mnt/z/.tmp_home
# Run your command
```

**For pytest (which also hits `/tmp` issues):**
```bash
mkdir -p ./.tmp
TMPDIR=./.tmp pytest tests/
```

### Why This Matters
This issue is the root cause of multiple seemingly-unrelated failures: git config errors, opencode "Permission denied" (exit 126), pytest tmpfile crashes, and `sudo` being completely broken. When diagnosing WSL tool failures, always check `ls -la /home/<user>/` first.

## `/tmp` Permission Denied (os error 13)

A distinct WSL issue: `/tmp` is root-owned with the sticky bit (`drwxrwxrwt`), and some tools (notably `uv`, `pytest`, anything using `tempfile.mkstemp`) fail when trying to write temporary files there.

### Symptom
```bash
$ uv add arize-phoenix-otel
error: Permission denied (os error 13) at path "/tmp/.tmpTYjfhv"

$ pytest tests/
FileNotFoundError: [Errno 2] No such file or directory
# pytest's capture plugin tries to snap /tmp-based temp files
```

### Root Cause
The WSL session user does not have write permission to `/tmp` due to WSL's permission mapping quirks. This is NOT a standard Linux `/tmp` — it's a WSL virtual tmpfs where the sticky-bit semantics don't map cleanly to the Windows user identity.

### Fix
Set `TMPDIR` to a project-local writable directory:
```bash
mkdir -p ./.tmp
TMPDIR=./.tmp uv add arize-phoenix-otel
TMPDIR=./.tmp pytest tests/
```

For `uv` specifically, also set `UV_CACHE_DIR`:
```bash
mkdir -p ./.uv_cache
TMPDIR=./.tmp UV_CACHE_DIR=./.uv_cache uv sync
```

**Do NOT** try `sudo`, `chmod 777 /tmp`, or `chown` on `/tmp` — these are unreliable inside WSL and may break other WSL services.

### Why this matters for OpenCode
OpenCode's `opencode run --instruction -` (piping markdown to stdin) writes the instruction content to `/tmp` before processing. On WSL this fails silently. **Always use `--file` instead:**
```bash
cat > PROJECT_PROMPT.md << 'EOF'
# Implementation instructions...
EOF
opencode run --file PROJECT_PROMPT.md --title "feature-name"
rm PROJECT_PROMPT.md
```

## Git Config Permission Denied

This is a **symptom** of the broader [Home Directory Permission Desync](#home-directory-permission-desync) issue above. When `~/.gitconfig` or `~/.config/git/ignore` become inaccessible, all `git` commands fail with:
```
fatal: unknown error occurred while reading the configuration files
warning: unable to access '/home/<user>/.gitconfig': Permission denied
warning: unable to access '/home/<user>/.config/git/ignore': Permission denied
```

### Fix
Run git with `GIT_CONFIG_GLOBAL=/dev/null` and `HOME=/tmp`:
```bash
HOME=/tmp GIT_CONFIG_GLOBAL=/dev/null git status --short
HOME=/tmp GIT_CONFIG_GLOBAL=/dev/null git diff --stat
```

For scripts that need git info, export both before the command block:
```bash
export HOME=/tmp
export GIT_CONFIG_GLOBAL=/dev/null
git -C /path/to/repo status --short
```

**Note:** This disables git config (aliases, user.name, etc.) for that invocation only. Use it for read-only operations like `status`, `diff`, `log`. Do NOT use it for operations that need your identity (commits, pushes).

### Enhanced Workaround: Fake Home Directory

When `HOME=/tmp GIT_CONFIG_GLOBAL=/dev/null` still fails because git tries to read `~/.config/git/ignore` under the temporary home, create a minimal fake home directory:

```bash
mkdir -p /tmp/fakehome/.config/git
HOME=/tmp/fakehome git -C /path/to/repo status --short
```

This works because:
- `/tmp/fakehome/.config/git/` exists and is traversable
- Git no longer trips over the inaccessible real `~/.config/git/ignore`
- The fake home is owned by the current user (since `/tmp` is root-owned but sticky-bit, any user can create files there)

**For complex git operations across multiple repos:**
```bash
mkdir -p /tmp/fakehome/.config/git
for repo in /mnt/z/pantheon/.pantheon /mnt/z/pantheon/projects/purple-phoenix/tasks/288-*; do
  echo "=== $repo ==="
  HOME=/tmp/fakehome git -C "$repo" status --short
  HOME=/tmp/fakehome git -C "$repo" diff --stat master..HEAD
done
```

This pattern is especially useful when you need to investigate task branches and worktrees while the home directory desync is active — it avoids the permission errors that would otherwise block every `git` invocation.

## Related Skills
- `wsl-localhost` — WSL2 localhost forwarding issues (separate networking concern)

## References
- `references/drvfs-permissions.md` — detailed session notes on Permission denied at mount root
- `references/tmp-and-git-permissions.md` — `/tmp` and git config permission desync
- `references/inotify-drvfs-limitation.md` — inotify does not work on WSL drvfs (9p) mounts; use PollingObserver fallback