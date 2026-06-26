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
    """Download the latest vet binary from GitHub."""
    machine = platform.machine().lower()
    system = platform.system().lower()

    # vet releases are at github.com/vet-run/vet/releases
    # The install script is the canonical distribution method
    url = "https://getvet.sh/install.sh"

    print(f"Downloading vet...")

    with tempfile.TemporaryDirectory() as tmpdir:
        install_script = Path(tmpdir) / "install.sh"
        urlretrieve(url, install_script)

        # The install script downloads vet to /usr/local/bin by default
        # We need to inspect it to find the actual binary URL
        script_content = install_script.read_text()

        # Extract the download URL from the script
        # Look for pattern like: https://github.com/vet-run/vet/releases/download/...
        import re

        match = re.search(r'https://github\.com/vet-run/vet/releases/download/[^"\'\s]+', script_content)
        if match:
            binary_url = match.group(0)
            # Determine the correct binary name based on platform
            if system == "darwin":
                binary_name = "vet-darwin-amd64" if machine in ("x86_64", "amd64") else "vet-darwin-arm64"
            else:
                binary_name = "vet-linux-amd64" if machine in ("x86_64", "amd64") else "vet-linux-arm64"

            # Try to construct the binary URL
            base_url = binary_url.rsplit("/", 1)[0]
            binary_url = f"{base_url}/{binary_name}"

            try:
                urlretrieve(binary_url, VET_PATH)
                VET_PATH.chmod(VET_PATH.stat().st_mode | stat.S_IEXEC)
                print(f"vet installed to {VET_PATH}")
                return VET_PATH
            except Exception:
                # Fall back: the vet script itself is the tool
                # It's a bash script, so we can use it directly
                shutil.copy2(install_script, VET_PATH)
                VET_PATH.chmod(VET_PATH.stat().st_mode | stat.S_IEXEC)
                print(f"vet install script saved to {VET_PATH}")
                return VET_PATH
        else:
            raise RuntimeError("Could not find vet download URL in install script")


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
