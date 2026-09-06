#!/usr/bin/env python3
"""Download ShellCheck and vet binaries for the security plugin."""

import os
import platform
import shutil
import stat
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlretrieve

PLUGIN_DIR = Path(__file__).parent
SHELLCHECK_PATH = PLUGIN_DIR / "shellcheck"
VET_PATH = PLUGIN_DIR / "vet"


def download_shellcheck() -> Path:
    """Download the latest ShellCheck binary."""
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

    print(f"Downloading ShellCheck for {system} {machine}...")

    with tempfile.TemporaryDirectory() as tmpdir:
        archive = Path(tmpdir) / "shellcheck.tar.xz"
        urlretrieve(url, archive)

        with tarfile.open(archive, "r:xz") as tf:
            # Find the shellcheck binary inside the archive
            for member in tf.getmembers():
                if member.name.endswith("/shellcheck") or member.name == "shellcheck":
                    tf.extract(member, tmpdir)
                    extracted = Path(tmpdir) / member.name
                    shutil.copy2(extracted, SHELLCHECK_PATH)
                    SHELLCHECK_PATH.chmod(SHELLCHECK_PATH.stat().st_mode | stat.S_IEXEC)
                    print(f"ShellCheck installed to {SHELLCHECK_PATH}")
                    return SHELLCHECK_PATH

    raise RuntimeError("Could not find shellcheck binary in archive")


def download_vet() -> Path:
    """Download the latest vet script from GitHub releases.

    vet is distributed as a single bash script, not a platform binary.
    """
    # Direct download from GitHub latest release
    url = "https://github.com/vet-run/vet/releases/latest/download/vet"

    print(f"Downloading vet from {url} ...")

    urlretrieve(url, VET_PATH)
    VET_PATH.chmod(VET_PATH.stat().st_mode | stat.S_IEXEC)
    print(f"vet installed to {VET_PATH}")
    return VET_PATH


def ensure_binaries() -> tuple[Path | None, Path | None]:
    """Ensure both binaries are available, downloading if necessary."""
    shellcheck = None
    vet = None

    if not SHELLCHECK_PATH.exists():
        try:
            shellcheck = download_shellcheck()
        except Exception as e:
            print(f"Warning: Could not download ShellCheck: {e}")
    else:
        shellcheck = SHELLCHECK_PATH

    if not VET_PATH.exists():
        try:
            vet = download_vet()
        except Exception as e:
            print(f"Warning: Could not download vet: {e}")
    else:
        vet = VET_PATH

    return shellcheck, vet


if __name__ == "__main__":
    sc, vt = ensure_binaries()
    if sc:
        print(f"ShellCheck: {sc} ✓")
    else:
        print("ShellCheck: not available")
    if vt:
        print(f"vet: {vt} ✓")
    else:
        print("vet: not available")
