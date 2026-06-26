"""Shell security plugin for Hermes.

Validates shell commands before execution using ShellCheck and vet.
Hooks into pre_tool_call for terminal and execute_code tools.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────

_SHELLCHECK_PATH: str = ""
_VET_PATH: str = ""
_BLOCK_ON_ERROR: bool = True
_WARN_ON_WARNING: bool = True
_MAX_SCRIPT_SIZE: int = 100_000
_ALLOWED_SCHEMES: list[str] = ["https"]

# Patterns that indicate a shell command
_SHELL_PATTERNS = [
    re.compile(r"\b(?:bash|sh|zsh|fish|dash|ksh|csh|tcsh)\s+-c\s+['\"]"),
    re.compile(r"\bcurl\s+.*\|\s*(?:bash|sh|zsh|fish|dash|ksh)"),
    re.compile(r"\bwget\s+.*\|\s*(?:bash|sh|zsh|fish|dash|ksh)"),
    re.compile(r"\b(?:curl|wget)\s+.*\s+-O\s+.*\.(?:sh|bash|zsh)"),
]

# Dangerous patterns that should always be blocked
_DANGEROUS_PATTERNS = [
    re.compile(r"\brm\s+-rf\s+/"),
    re.compile(r"\bdd\s+if=.*of=/dev/(?:sd|hd|disk)"),
    re.compile(r"\bmv\s+/\s+.*"),
    re.compile(r"\bchmod\s+777\s+/"),
    re.compile(r"\bmkfs\."),
    re.compile(r"\b>:\s*\(\)"),  # Fork bomb
    re.compile(r"\bwget\s+.*\|\s*(?:bash|sh)\s+-c\s+.*rm\s+-rf"),
]


def _init_config() -> None:
    """Load configuration from environment variables."""
    global _SHELLCHECK_PATH, _VET_PATH, _BLOCK_ON_ERROR, _WARN_ON_WARNING
    global _MAX_SCRIPT_SIZE, _ALLOWED_SCHEMES

    _SHELLCHECK_PATH = os.environ.get("HERMES_SHELLCHECK_PATH", "")
    _VET_PATH = os.environ.get("HERMES_VET_PATH", "")
    _BLOCK_ON_ERROR = os.environ.get("HERMES_BLOCK_ON_ERROR", "true").lower() == "true"
    _WARN_ON_WARNING = os.environ.get("HERMES_WARN_ON_WARNING", "true").lower() == "true"
    _MAX_SCRIPT_SIZE = int(os.environ.get("HERMES_MAX_SCRIPT_SIZE", "100000"))
    schemes = os.environ.get("HERMES_ALLOWED_SCHEMES", "https")
    _ALLOWED_SCHEMES = [s.strip() for s in schemes.split(",")]


def _find_binary(name: str, env_var: str, default_paths: list[str]) -> str | None:
    """Find a binary in PATH or default locations."""
    # Check environment variable first
    path = os.environ.get(env_var, "")
    if path and Path(path).exists():
        return path

    # Check PATH
    found = shutil.which(name)
    if found:
        return found

    # Check default locations
    for p in default_paths:
        if Path(p).exists():
            return p

    return None


def _get_shellcheck() -> str | None:
    """Find shellcheck binary, downloading if necessary."""
    plugin_dir = Path(__file__).parent
    local_binary = plugin_dir / "shellcheck"

    # Check local binary first
    if local_binary.exists():
        return str(local_binary)

    # Check PATH
    found = shutil.which("shellcheck")
    if found:
        return found

    # Try to download
    try:
        from .download_binaries import ensure_binaries

        sc, _ = ensure_binaries()
        if sc:
            return str(sc)
    except Exception:
        pass

    return None


def _get_vet() -> str | None:
    """Find vet binary, downloading if necessary."""
    plugin_dir = Path(__file__).parent
    local_binary = plugin_dir / "vet"

    # Check local binary first
    if local_binary.exists():
        return str(local_binary)

    # Check PATH
    found = shutil.which("vet")
    if found:
        return found

    # Try to download
    try:
        from .download_binaries import ensure_binaries

        _, vt = ensure_binaries()
        if vt:
            return str(vt)
    except Exception:
        pass

    return None


def _is_shell_command(command: str) -> bool:
    """Check if a command looks like shell code."""
    # Check for shell patterns
    for pattern in _SHELL_PATTERNS:
        if pattern.search(command):
            return True

    # Check if it contains shell syntax
    shell_indicators = [";", "&&", "||", "|", "$(", "`", "if ", "for ", "while ", "function "]
    if any(ind in command for ind in shell_indicators):
        return True

    return False


def _has_dangerous_patterns(command: str) -> list[str]:
    """Check for dangerous patterns in a command."""
    findings = []
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(command):
            findings.append(f"Dangerous pattern detected: {pattern.pattern}")
    return findings


def _run_shellcheck(script: str) -> dict[str, Any]:
    """Run shellcheck on a script and return results."""
    shellcheck = _get_shellcheck()
    if not shellcheck:
        return {"available": False, "error": "shellcheck not found"}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write(script)
        tmp_path = f.name

    result_stdout = ""
    try:
        result = subprocess.run(
            [shellcheck, "--format=json", "--shell=bash", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        result_stdout = result.stdout

        if result_stdout:
            issues = json.loads(result_stdout)
            errors = [i for i in issues if i.get("severity") == "error"]
            warnings = [i for i in issues if i.get("severity") == "warning"]
            infos = [i for i in issues if i.get("severity") not in ("error", "warning")]

            return {
                "available": True,
                "issues": issues,
                "errors": errors,
                "warnings": warnings,
                "infos": infos,
                "has_errors": len(errors) > 0,
                "has_warnings": len(warnings) > 0,
            }
        else:
            return {"available": True, "issues": [], "has_errors": False, "has_warnings": False}
    except json.JSONDecodeError:
        return {"available": True, "error": "Failed to parse shellcheck output", "raw": result_stdout}
    except subprocess.TimeoutExpired:
        return {"available": True, "error": "shellcheck timed out"}
    except Exception as e:
        return {"available": True, "error": str(e)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _format_issues(issues: list[dict]) -> str:
    """Format shellcheck issues for display."""
    lines = []
    for issue in issues[:20]:  # Limit to first 20
        severity = issue.get("severity", "unknown").upper()
        code = issue.get("code", "?")
        msg = issue.get("message", "No message")
        line = issue.get("line", "?")
        lines.append(f"  [{severity}] Line {line}: SC{code} - {msg}")
    if len(issues) > 20:
        lines.append(f"  ... and {len(issues) - 20} more issues")
    return "\n".join(lines)


def _check_remote_script(command: str) -> dict[str, Any]:
    """Check if command downloads and executes a remote script."""
    # Pattern: curl/wget ... | bash/sh
    remote_pattern = re.compile(
        r"(?:curl|wget)\s+.*?(https?://\S+).*?\|\s*(?:bash|sh|zsh|dash|ksh|fish)"
    )
    match = remote_pattern.search(command)

    if not match:
        return {"is_remote": False}

    url = match.group(1)
    scheme = url.split("://")[0] if "://" in url else ""

    if scheme not in _ALLOWED_SCHEMES:
        return {
            "is_remote": True,
            "url": url,
            "blocked": True,
            "reason": f"URL scheme '{scheme}' not in allowed schemes: {_ALLOWED_SCHEMES}",
        }

    vet = _get_vet()
    if vet:
        # vet is interactive, so we can't use it in automation
        # Instead, warn about remote script execution
        return {
            "is_remote": True,
            "url": url,
            "blocked": False,
            "warning": f"Remote script execution detected: {url}. Consider using 'vet {url}' to inspect before executing.",
        }

    return {
        "is_remote": True,
        "url": url,
        "blocked": False,
        "warning": f"Remote script execution detected: {url}",
    }


def on_pre_tool_call(
    tool_name: str,
    args: dict[str, Any],
    tool_call_id: str,
    task_id: str = "",
    session_id: str = "",
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Validate shell commands before execution.

    Returns a block directive if the command is dangerous or has errors.
    """
    if tool_name not in ("terminal", "execute_code"):
        return None

    _init_config()

    command = args.get("command", "") if isinstance(args, dict) else str(args)

    if not command:
        return None

    # Skip if script is too large
    if len(command) > _MAX_SCRIPT_SIZE:
        return None  # Too large to scan efficiently

    # Check for dangerous patterns first
    dangers = _has_dangerous_patterns(command)
    if dangers:
        return {
            "action": "block",
            "message": f"SECURITY BLOCK: Dangerous command detected:\n" + "\n".join(dangers),
        }

    # Check for remote script execution
    remote_check = _check_remote_script(command)
    if remote_check.get("blocked"):
        return {
            "action": "block",
            "message": f"SECURITY BLOCK: {remote_check['reason']}\nURL: {remote_check['url']}",
        }

    # Run shellcheck if it looks like shell code
    if _is_shell_command(command):
        result = _run_shellcheck(command)

        if result.get("has_errors") and _BLOCK_ON_ERROR:
            issues = _format_issues(result.get("errors", []))
            message = f"SECURITY BLOCK: ShellCheck found errors in command:\n{issues}"
            if remote_check.get("warning"):
                message += f"\n\n{remote_check['warning']}"
            return {"action": "block", "message": message}

        if result.get("has_warnings") and _WARN_ON_WARNING:
            issues = _format_issues(result.get("warnings", []))
            message = f"SECURITY WARNING: ShellCheck found warnings:\n{issues}"
            if remote_check.get("warning"):
                message += f"\n\n{remote_check['warning']}"
            return {"action": "warn", "message": message}

    if remote_check.get("warning"):
        return {"action": "warn", "message": remote_check["warning"]}

    return None


def register(ctx) -> None:
    """Register the security plugin."""
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
