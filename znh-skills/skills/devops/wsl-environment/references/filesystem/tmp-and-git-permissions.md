# WSL /tmp and Git Permission Issues — Session Notes

## Session Context
- Date: 2026-06-25
- Project: purple-phoenix (Pantheon)
- Task: Integrate Phoenix (Arize) OTEL tracing instrumentation
- WSL2, `networkingMode=Mirrored`

## `/tmp` Blocks uv, pytest, OpenCode

### Symptom
```bash
$ uv add arize-phoenix-otel
error: failed to open file `/mnt/z/.uv_cache/sdists-v9/.git`: Permission denied (os error 13)

$ uv add arize-phoenix-otel
error: Permission denied (os error 13) at path "/tmp/.tmpTYjfhv"

$ pytest tests/
FileNotFoundError: [Errno 2] No such file or directory
# at _pytest/capture.py line 594 — snap() on /tmp-based tempfile
```

### Root Cause
`/tmp` is root-owned with sticky bit. WSL's permission mapping does not allow the session user to write there reliably. This affects any tool using Python's `tempfile` module or Rust's `tempfile` crate (which `uv` uses).

### What Did NOT Work
- `sudo` — broken in same permission state (`libsudo_util.so.0: cannot open shared object file`)
- `chmod 755 /tmp` — fails silently or reports success without effect
- `UV_CACHE_DIR=/tmp/uv_cache` — still fails because `uv` writes to `/tmp` for build artifacts

### What Worked
```bash
mkdir -p ./.tmp
TMPDIR=./.tmp UV_CACHE_DIR=./.uv_cache uv add arize-phoenix-otel
# Resolved 103 packages, built pantheon, installed 14 packages — success

TMPDIR=./.tmp pytest tests/test_daemon.py -v -s
# 14 passed — success
```

### Cleanup
After the operation, remove the temp directories:
```bash
rm -rf ./.tmp ./.uv_cache
```

## Git Config Permission Denied

### Symptom
```bash
$ git status --short
warning: unable to access '/home/znh/.gitconfig': Permission denied
warning: unable to access '/home/znh/.gitconfig': Permission denied
fatal: unknown error occurred while reading the configuration files
```

Same for `.config/git/ignore`:
```bash
$ git status --short
warning: unable to access '/home/znh/.config/git/ignore': Permission denied
fatal: cannot use /home/znh/.config/git/ignore as an exclude file
```

### Fix
```bash
chmod 755 /home/znh/.config       # fixes the .config/git/ignore issue
HOME=/tmp GIT_CONFIG_GLOBAL=/dev/null git -C /path/to/repo status --short
```

### Enhanced Fix (When chmod Also Fails)

When `sudo` and `chmod` are both broken in the same permission desync state, create a minimal fake home directory:

```bash
mkdir -p /tmp/fakehome/.config/git
HOME=/tmp/fakehome git -C /path/to/repo status --short
```

This avoids both the `.gitconfig` and `.config/git/ignore` permission errors by giving git a fully traversable home directory.

For batch operations across multiple repos (e.g., checking Pantheon task branches):
```bash
mkdir -p /tmp/fakehome/.config/git
for repo in /mnt/z/pantheon/.pantheon /mnt/z/pantheon/projects/purple-phoenix/tasks/*; do
  echo "=== $(basename $repo) ==="
  HOME=/tmp/fakehome git -C "$repo" status --short 2>/dev/null || echo "  not a repo"
done
```

### Full Script Pattern
```bash
export HOME=/tmp
export GIT_CONFIG_GLOBAL=/dev/null

git -C /mnt/z/pantheon/.pantheon status --short
git -C /mnt/z/pantheon/.pantheon diff --stat
git -C /mnt/z/pantheon/.pantheon diff agent_context/scripts/worker.py
```

## Cross-Issue Pattern
Both `/tmp` and git failures share the same root cause: WSL2 permission desync on the home directory (`/home/<user>/`) and its subdirectories (`.config/`, `.gitconfig`, etc.). The `/tmp` issue is separate but often co-occurs because WSL's permission state is fragile after Windows updates or sleep/hibernate.

### Diagnostic Sequence
When ANY WSL tool fails with "Permission denied" unexpectedly:
1. `ls -la /home/<user>/` — if this fails, it's the home-dir desync
2. `ls -la /tmp` — if owned by root, the `/tmp` issue is active
3. Check if the tool uses temp files: `strace -e open,openat <command> 2>&1 | grep /tmp` (if available)
4. Fix home dir: `wsl --shutdown` from Windows, then restart
5. Fix `/tmp` for current session: `mkdir -p ./.tmp && TMPDIR=./.tmp <command>`
