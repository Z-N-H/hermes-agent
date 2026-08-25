# inotify Does Not Work on WSL drvfs (9p) Mounts

## Session Context
- Date: 2026-06-27
- Project: ZNH Obsidian vault trigger scanner
- WSL2, vault on `/mnt/z` (drvfs/9p mount)

## Symptom

A Python `watchdog.Observer` watching `/mnt/z/pantheon/vault/ZNH/` receives **zero file change events**, even when files are actively being created and modified:

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class Handler(FileSystemEventHandler):
    def on_modified(self, event):
        print(f"Modified: {event.src_path}")


observer = Observer()
observer.schedule(Handler(), "/mnt/z/pantheon/vault/ZNH", recursive=True)
observer.start()
# ...create, modify, delete files...
# Output: nothing. Zero events.
```

The same code on a native ext4 filesystem works perfectly.

## Root Cause

WSL2 mounts Windows drives via the **9p (Plan 9) filesystem** using `drvfs`. The 9p protocol does **not** implement Linux `inotify` semantics. `inotify` watches are inode-based and require kernel-level filesystem support that 9p simply does not provide.

**Filesystem type detection:**
```bash
$ findmnt -T /mnt/z/pantheon/vault/ZNH
TARGET                    SOURCE    FSTYPE OPTIONS
/mnt/z                    Z:\       9p     rw,...
```

Or read `/proc/mounts`:
```bash
$ grep /mnt/z /proc/mounts
Z:\ /mnt/z 9p rw,... 0 0
```

Any filesystem type in the `9p` family (drvfs, 9p, CIFS, SMB, NFS, FUSE, ceph, glusterfs) will have this limitation.

## Fix — PollingObserver Fallback

`watchdog` provides `PollingObserver` which polls the filesystem at a configured interval instead of using inotify. It has the same event API (`on_modified`, `on_created`, etc.) but works on any filesystem.

```python
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
import time


class Handler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory:
            return
        print(f"Modified: {event.src_path}")


# Use PollingObserver on 9p/drvfs/CIFS/NFS/FUSE filesystems
observer = PollingObserver(timeout=1.0)  # poll every 1 second
observer.schedule(Handler(), "/mnt/z/pantheon/vault/ZNH", recursive=True)
observer.start()
```

**Auto-detection pattern** (used in the vault trigger scanner):
```python
import os
from pathlib import Path

POLLING_FS_TYPES = {
    "9p",
    "cifs",
    "smbfs",
    "nfs",
    "nfs4",
    "fuse",
    "fuseblk",
    "ceph",
    "glusterfs",
}


def _get_fs_type(path: Path) -> str:
    mount_point = str(path.resolve())
    while not os.path.ismount(mount_point):
        parent = os.path.dirname(mount_point)
        if parent == mount_point:
            break
        mount_point = parent
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and parts[1] == mount_point:
                    return parts[2]
    except OSError:
        pass
    return ""


def create_observer(path: Path, timeout: float = 1.0):
    fs_type = _get_fs_type(path)
    if fs_type in POLLING_FS_TYPES:
        from watchdog.observers.polling import PollingObserver

        return PollingObserver(timeout=timeout)
    from watchdog.observers import Observer

    return Observer()
```

## Trade-offs

| | `Observer` (inotify) | `PollingObserver` |
|---|---|---|
| **Latency** | Near-instant (kernel event) | ~1 second (poll interval) |
| **CPU usage** | Negligible (kernel callback) | Low (stat on watched files) |
| **Works on 9p/drvfs** | ❌ No | ✅ Yes |
| **Works on ext4/btrfs** | ✅ Yes | ✅ Yes |

For a vault scanner watching ~1,000 markdown files, `PollingObserver` with a 1-second interval uses negligible CPU but provides fast-enough detection for UX purposes.

## When to Use

- Any Python tool that needs file watching on `/mnt/c`, `/mnt/d`, `/mnt/z`, or any WSL-mounted Windows drive
- Background services (systemd) that watch vaults or project directories on drvfs
- File-based build systems, auto-reload dev servers, or sync tools running in WSL against Windows filesystems

## Related

- `wsl-localhost` — for networking quirks, not filesystem
- `wsl-filesystem` home directory desync — a separate WSL permission issue that often co-occurs but has a different root cause and fix
