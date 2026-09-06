# Hermes Plugin — Auto-Download External Binaries Pattern

Session: 2026-06-26 — Building the ShellCheck security plugin for Hermes.

## The Problem

Plugins often need external binaries (ShellCheck, vet, playwright, ffmpeg, etc.). Committing them to git bloats the repo:
- ShellCheck binary: ~15 MB
- vet binary: ~5 MB
- Large binaries in git slow clones, inflate diffs, and can't be updated without a new commit

## The Solution

1. **Exclude binaries from git** with `.gitignore`
2. **Include a download script** that fetches the right binary for the current platform on first use
3. **Check multiple locations** — local plugin dir, PATH, then auto-download
4. **Graceful degradation** — if download fails, the plugin continues without the binary

## File Layout

```
plugins/security/
├── .gitignore              # Excludes *.tar.xz, shellcheck, vet
├── __init__.py             # Plugin logic — calls download on demand
├── download_binaries.py    # Platform-aware downloader
├── plugin.yaml             # Manifest
└── tests/
    └── test_security_plugin.py
```

## .gitignore

```gitignore
# Security plugin binaries — download on demand
*.tar.xz
shellcheck
vet
```

## download_binaries.py

```python
#!/usr/bin/env python3
"""Download external binaries for the security plugin."""

import os
import platform
import shutil
import stat
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlretrieve

PLUGIN_DIR = Path(__file__).parent


def download_shellcheck() -> Path:
    """Download ShellCheck for the current platform."""
    machine = platform.machine().lower()
    system = platform.system().lower()

    if system == "linux" and machine in ("x86_64", "amd64"):
        url = "https://github.com/koalaman/shellcheck/releases/download/v0.10.0/shellcheck-v0.10.0.linux.x86_64.tar.xz"
    elif system == "linux" and machine in ("aarch64", "arm64"):
        url = "https://github.com/koalaman/shellcheck/releases/download/v0.10.0/shellcheck-v0.10.0.linux.aarch64.tar.xz"
    elif system == "darwin" and machine in ("x86_64", "amd64"):
        url = "https://github.com/koalaman/shellcheck/releases/download/v0.10.0/shellcheck-v0.10.0.darwin.x86_64.tar.xz"
    elif system == "darwin" and machine in ("aarch64", "arm64"):
        url = "https://github.com/koalaman/shellcheck/releases/download/v0.10.0/shellcheck-v0.10.0.darwin.aarch64.tar.xz"
    else:
        raise RuntimeError(f"Unsupported platform: {system} {machine}")

    with tempfile.TemporaryDirectory() as tmpdir:
        archive = Path(tmpdir) / "shellcheck.tar.xz"
        urlretrieve(url, archive)

        with tarfile.open(archive, "r:xz") as tf:
            for member in tf.getmembers():
                if member.name.endswith("/shellcheck") or member.name == "shellcheck":
                    tf.extract(member, tmpdir)
                    extracted = Path(tmpdir) / member.name
                    dest = PLUGIN_DIR / "shellcheck"
                    shutil.copy2(extracted, dest)
                    dest.chmod(dest.stat().st_mode | stat.S_IEXEC)
                    return dest

    raise RuntimeError("Could not find shellcheck binary in archive")
```

## __init__.py — on-demand binary resolution

```python
def _get_shellcheck() -> str | None:
    """Find shellcheck binary, downloading if necessary."""
    plugin_dir = Path(__file__).parent
    local_binary = plugin_dir / "shellcheck"

    # 1. Check local binary first
    if local_binary.exists():
        return str(local_binary)

    # 2. Check PATH
    found = shutil.which("shellcheck")
    if found:
        return found

    # 3. Try to download
    try:
        from .download_binaries import ensure_binaries

        sc, _ = ensure_binaries()
        if sc:
            return str(sc)
    except Exception:
        pass

    return None
```

## Key Design Decisions

1. **Local binary takes precedence** — if the user manually installed a newer version, use it
2. **PATH is second** — system package manager installations are respected
3. **Auto-download is last** — only runs when no other source is available
4. **Exceptions are swallowed** — the plugin continues without the binary, logging a warning
5. **Platform detection** — `platform.machine()` and `platform.system()` handle Linux/macOS x86_64/ARM64

## Variant: Single-Script Distribution (Not Platform Binary)

Some tools are distributed as a single cross-platform script, not as platform-specific binaries. **Do not apply platform-detection logic to these.**

### Example: `vet` (https://github.com/vet-run/vet)

`vet` is a single bash script. The correct download URL:
```
https://github.com/vet-run/vet/releases/latest/download/vet
```

**Wrong approach (HTTP 403):**
```python
# INCORRECT — these URLs do not exist
urls = {
    ("linux", "x86_64"): ".../vet-linux-amd64",
    ("linux", "aarch64"): ".../vet-linux-arm64",
    ("darwin", "x86_64"): ".../vet-darwin-amd64",
    ("darwin", "arm64"): ".../vet-darwin-arm64",
}
```

**Correct approach:**
```python
def download_vet() -> Path:
    url = "https://github.com/vet-run/vet/releases/latest/download/vet"
    urlretrieve(url, VET_PATH)
    VET_PATH.chmod(VET_PATH.stat().st_mode | stat.S_IEXEC)
    return VET_PATH
```

**How to tell:** Check the project's GitHub Releases page. If there's only one asset named after the tool (not `tool-platform-arch`), it's a single-script distribution. The `getvet.sh/install.sh` script may also just be a thin wrapper that downloads the same script for everyone.

## Why Not Just `apt install shellcheck`?

- Not all environments have root access
- Different distros package different versions
- CI/test environments may not have package managers
- Pinning a specific release version avoids surprise build breaks

## Updating Binary Versions

Update the URL in `download_binaries.py` when a new release is available. The old binary will remain cached in the plugin directory; users can delete it to trigger a re-download.

## Verification After Download

After the downloader runs, verify both binaries are executable and functional:

```bash
# ShellCheck version check
plugins/security/shellcheck --version | head -2
# Expected: "ShellCheck - shell script analysis tool\nversion: 0.10.0"

# Vet help check
plugins/security/vet --help | head -3
# Expected: "vet v1.0.2 - A safer way to run remote scripts."
```

Then verify the plugin's hook functions work by importing the module directly:

```python
import importlib.util

spec = importlib.util.spec_from_file_location(
    "security", "plugins/security/__init__.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

assert module._get_shellcheck() is not None
assert module._get_vet() is not None
assert (
    module.on_pre_tool_call("terminal", {"command": "rm -rf /"}, "tc")["action"]
    == "block"
)
```

## Files from this session

- `/mnt/z/pantheon/.hermes/hermes-agent/plugins/security/download_binaries.py` — complete downloader
- `/mnt/z/pantheon/.hermes/hermes-agent/plugins/security/.gitignore` — binary exclusions
- `/mnt/z/pantheon/.hermes/hermes-agent/plugins/security/__init__.py` — on-demand resolution
