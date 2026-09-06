---
name: vet-remote-scripts
description: |
  Security workflow for executing remote shell scripts via vet (vet-run/vet).
  All install/setup .sh scripts downloaded from the internet MUST be inspected
  with vet before execution. This skill documents the command pattern,
  integration with the shell-security plugin, and when to apply it.
triggers:
  - User wants to run a remote install script (curl | bash, wget | sh)
  - A setup.sh, install.sh, or similar is downloaded from GitHub/releases
  - The shell-security plugin warns about remote script execution
  - Any .sh file from an external URL is about to be executed
steps:
  - |
    **Command pattern.** Always use vet to inspect before running:
    ```bash
    vet <URL> [SCRIPT_ARGUMENTS...]
    ```
    Examples:
    ```bash
    vet https://example.com/install.sh
    vet https://get.docker.com
    vet https://github.com/owner/repo/releases/latest/download/setup.sh
    ```
  - |
    **What vet does.** vet fetches the script, shows a diff against any
    previously cached version, runs it through a linter, and asks for explicit
    confirmation before executing. This prevents blindly trusting remote code.
  - |
    **Binary location.** The vet script is installed alongside the
    shell-security plugin:
    ```bash
    /mnt/z/pantheon/.hermes/hermes-agent/plugins/security/vet
    ```
    It is a self-contained bash script (v1.0.2, single file, no dependencies).
  - |
    **Hermes integration.** The `shell-security` plugin registers a
    `pre_tool_call` hook that fires on `terminal` and `execute_code` tools.
    When it detects `curl | bash` or `wget | sh` patterns, it emits a warning
    with the message:
    ```
    Remote script execution detected: <URL>. Consider using 'vet <URL>' to inspect before executing.
    ```
    This warning is non-blocking; the user or operator must choose to use vet.
  - |
    **Automation rule.** When the assistant itself generates a command that
    downloads and runs a remote .sh, it MUST route through vet instead of
    piping directly to the shell. Replace:
    ```bash
    curl -sSL https://example.com/install.sh | bash
    ```
    With:
    ```bash
    vet https://example.com/install.sh
    ```
  - |
    **When to apply.** Use vet for any of the following:
    - `curl ... | bash` or `curl ... | sh` patterns
    - `wget ... -O - | bash` patterns
    - Direct execution of a downloaded `.sh` from a GitHub release, CDN, or third-party site
    - Any install script, setup script, or bootstrap script from the internet
  - |
    **When NOT to apply.** Vet is unnecessary for:
    - Local scripts (already on disk, not downloaded)
    - Scripts from your own git repository that you have already reviewed
    - Package manager installs (`apt install`, `pip install`, `npm install`) — these are already sandboxed
    - One-liner commands that do not download external code (`echo`, `ls`, `mkdir`)
  - |
    **Force mode (dangerous).** vet has a `-f` / `--force` flag that skips
    the interactive prompt. Never use this in automated workflows unless the
    URL is from a trusted first-party source (e.g., your own release assets).
    ```bash
    vet -f https://your-own-domain.com/setup.sh   # only if you own the domain
    ```
pitfalls:
  - |
    vet is interactive and requires a TTY. In non-interactive environments
    (cron jobs, CI pipelines, background processes), vet will hang waiting
    for user input. In those cases, use the force flag only after human review,
    or download the script first, inspect it manually, then run it.
  - |
    Do not confuse `vet-run/vet` (script inspector) with `safedep/vet`
    (malicious package scanner). They are different tools with the same name.
    The security plugin uses `vet-run/vet`.
  - |
    The vet binary is downloaded on first use by `download_binaries.py`.
    If the download fails (network issues), the shell-security plugin falls
    back to a plain text warning without the vet integration.
  - |
    vet caches scripts in `~/.cache/vet/`. It will show a diff if the script
    has changed since the last inspection. This is a feature, not a bug — it
    helps detect tampering.
verification:
  - |
    Verify vet is installed:
    ```bash
    /mnt/z/pantheon/.hermes/hermes-agent/plugins/security/vet --help
    ```
  - |
    Verify the shell-security plugin is enabled:
    ```bash
    hermes plugins list | grep shell-security
    ```
    Should show `enabled`.
  - |
    Trigger a test warning by asking Hermes to run:
    ```bash
    curl -sSL https://example.com/install.sh | bash
    ```
    The plugin should return a warning mentioning vet.
references:
  - https://getvet.sh
  - https://github.com/vet-run/vet
  - plugins/security/__init__.py (shell-security plugin hook)
  - plugins/security/download_binaries.py (auto-download logic)
---

# vet Remote Scripts

## Rule

**All install or setup `.sh` scripts downloaded from the internet MUST be run via `vet` before execution.**

## Quick Reference

| Pattern | Instead of... | Use... |
|---|---|---|
| `curl \| bash` | `curl -sSL https://x.com/install.sh \| bash` | `vet https://x.com/install.sh` |
| `wget \| sh` | `wget -qO- https://x.com/setup.sh \| sh` | `vet https://x.com/setup.sh` |
| GitHub release | `curl -L https://github.com/.../install.sh \| bash` | `vet https://github.com/.../install.sh` |
| CDN script | `curl https://cdn.example.com/bootstrap.sh \| bash` | `vet https://cdn.example.com/bootstrap.sh` |

## Why vet

`vet` (from [vet-run/vet](https://github.com/vet-run/vet)) fetches a remote script, caches it, shows a diff against the previous version (if any), runs it through a linter, and requires explicit confirmation before execution. It is the safest way to handle the `curl | bash` anti-pattern.

## Hermes Integration

The `shell-security` plugin is already enabled in your Hermes config. When a `terminal` or `execute_code` tool call matches a remote script pattern, the plugin emits:

> Remote script execution detected: `<URL>`. Consider using 'vet `<URL>`' to inspect before executing.

As the assistant, when you generate such commands, **pre-empt this warning by using vet directly**.

## Examples

### Docker install
```bash
# Unsafe (don't do this)
curl -sSL https://get.docker.com | bash

# Safe
vet https://get.docker.com
```

### Homebrew install
```bash
# Unsafe
curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh | bash

# Safe
vet https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh
```

### Custom release asset
```bash
vet https://github.com/your-org/your-repo/releases/latest/download/setup.sh
```

## When vet is not needed

- Local scripts you have already reviewed
- Package manager commands (`apt`, `pip`, `npm`, `brew`) — already sandboxed
- Simple one-liners that do not download external code

## Automation Note

vet requires a TTY and is interactive. In non-interactive contexts (CI, cron), either:
1. Download the script first, review it, then run with `vet -f <URL>` (force mode)
2. Or skip vet and review the script manually before execution

Do **not** use `vet -f` on untrusted URLs.