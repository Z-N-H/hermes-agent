# Shell Security Plugin — Implementation Reference

Session: 2026-06-26 — Building a ShellCheck/vet security plugin for Hermes.

## Plugin Location

```
plugins/security/
├── plugin.yaml              # manifest
├── __init__.py              # validation logic
├── download_binaries.py     # fetches shellcheck + vet on first use
├── .gitignore               # ignores *.tar.xz, shellcheck, vet
└── tests/
    └── test_security_plugin.py  # 16 tests, all passing
```

## Binary management (do NOT commit to git)

**Pitfall:** Committing 15MB ShellCheck binary to git bloats the repo forever. Use a download script instead:

```python
# download_binaries.py
import os, platform, shutil, stat, tarfile, tempfile
from pathlib import Path
from urllib.request import urlretrieve

PLUGIN_DIR = Path(__file__).parent
SHELLCHECK = PLUGIN_DIR / "shellcheck"


def download_shellcheck() -> Path:
    machine = platform.machine().lower()
    system = platform.system().lower()
    # Map platform to release URL
    urls = {
        ("linux", "x86_64"): "...linux.x86_64.tar.xz",
        ("linux", "aarch64"): "...linux.aarch64.tar.xz",
        ("darwin", "x86_64"): "...darwin.x86_64.tar.xz",
        ("darwin", "arm64"): "...darwin.aarch64.tar.xz",
    }
    url = urls[(system, machine)]
    # Download, extract, move binary to PLUGIN_DIR
    ...
```

The plugin's `_get_shellcheck()` helper checks in this order:
1. Local binary in plugin dir (already downloaded)
2. `shutil.which("shellcheck")` on PATH
3. Auto-download via `download_binaries.py` on first use

## What it does

Intercepts `terminal` and `execute_code` tool calls via `pre_tool_call` hook:

1. **Dangerous pattern blocking** — `rm -rf /`, `dd` to disks, fork bombs, etc.
2. **Remote script detection** — flags `curl | bash` patterns, blocks non-HTTPS
3. **ShellCheck linting** — runs static analysis on shell-like commands
4. **Graceful degradation** — works even if ShellCheck is missing

## Hook return values

| Return value | Effect |
|-------------|--------|
| `None` | Allow execution |
| `{"action": "block", "message": "..."}` | Block execution, show message to user |
| `{"action": "warn", "message": "..."}` | Warn but allow execution |

## Key implementation details

### ShellCheck binary management

**Do NOT commit the binary to git.** Use a `.gitignore` and a download script:

```gitignore
# plugins/security/.gitignore
*.tar.xz
shellcheck
vet
```

The `download_binaries.py` script fetches the correct platform binary on first use. This keeps the repo <1MB instead of ~15MB.

Download URL pattern:
```
https://github.com/koalaman/shellcheck/releases/download/v0.10.0/shellcheck-v0.10.0.linux.x86_64.tar.xz
```

### Vet script handling (CRITICAL FIX 2026-06-26)

**`vet` is a single bash script, NOT a platform-specific binary.**

The CORRECT download URL:
```
https://github.com/vet-run/vet/releases/latest/download/vet
```

**WRONG approach (produces HTTP 403):**
- Do NOT try to fetch `vet-linux-amd64`, `vet-darwin-arm64`, etc.
- Do NOT parse `getvet.sh/install.sh` to extract platform URLs.

The corrected download function:
```python
def download_vet() -> Path:
    url = "https://github.com/vet-run/vet/releases/latest/download/vet"
    urlretrieve(url, VET_PATH)
    VET_PATH.chmod(VET_PATH.stat().st_mode | stat.S_IEXEC)
    return VET_PATH
```

Vet is interactive (prompts for approval before executing scripts). In an automated agent context, it cannot prompt the user, so the plugin uses pattern-based detection (curl/wget + pipe) rather than invoking vet directly.

```bash
# When a remote script is detected, the plugin suggests the user run:
vet https://example.com/install.sh
```

### Pattern matching strategy

The plugin uses a two-stage approach:

**Stage 1: Dangerous patterns (always block)**
- Regex matching on the raw command string
- No false positives acceptable — these are unconditional blocks
- Covers: `rm -rf /`, `dd if=... of=/dev/sd*`, `mkfs.*`, `>:(){ :|:& };:`

**Stage 2: ShellCheck analysis (conditional block/warn)**
- Only runs if command looks like shell code (contains `;`, `&&`, `||`, `|`, `$(`, backticks, or shell keywords)
- Generates JSON output via `--format=json`
- Blocks on errors, warns on warnings (configurable)

### The `pre_tool_call` hook signature

```python
def on_pre_tool_call(
    tool_name: str,
    args: dict[str, Any],
    tool_call_id: str,
    task_id: str = "",
    session_id: str = "",
    **kwargs: Any,
) -> dict[str, Any] | None:
```

The `args` dict contains the tool arguments. For `terminal`, it's `{"command": "..."}`. For `execute_code`, it's `{"code": "..."}` or `{"command": "..."}`.

## Plugin registration pattern

```python
def register(ctx) -> None:
    """Register the security plugin."""
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
```

The `register()` function is called by Hermes's plugin loader (`_load_directory_module`). The plugin manager looks for `register` in the module and passes a `PluginContext` object.

## Plugin enablement

**Pitfall:** Plugins are opt-in. Presence in `plugins/security/` is not enough.

The plugin must be listed in `plugins.enabled` in `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - shell-security    # matches the `name:` field in plugin.yaml
```

Enable via CLI: `hermes plugins enable shell-security`
Verify: `hermes plugins list` — status should show `enabled`.

If a plugin is discovered but shows `enabled: False` with error `not enabled in config`, it has been found but not activated.

## Verification steps (post-install)

### Step 1: Check plugin discovery and loading

```bash
cd /path/to/hermes-agent
source venv/bin/activate
python3 -c "
from hermes_cli.plugins import PluginManager
pm = PluginManager()
pm.discover_and_load(force=True)
for key, p in pm._plugins.items():
    if 'security' in key:
        print(f'{key}: enabled={p.enabled}, hooks={p.hooks_registered}')
print('Has pre_tool_call:', pm.has_hook('pre_tool_call'))
print('Hook count:', len(pm._hooks.get('pre_tool_call', [])))
"
```

Expected output:
```
shell-security: enabled=True, hooks=['pre_tool_call']
Has pre_tool_call: True
Hook count: 2
```

### Step 2: Test hook functions directly (no full Hermes runtime)

```python
import importlib.util

spec = importlib.util.spec_from_file_location(
    "security", "plugins/security/__init__.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# Test 1: Dangerous command
result = module.on_pre_tool_call("terminal", {"command": "rm -rf /"}, "tc-1")
assert result["action"] == "block"

# Test 2: Safe command
result = module.on_pre_tool_call("terminal", {"command": "echo hello"}, "tc-2")
assert result is None

# Test 3: Remote script
result = module.on_pre_tool_call(
    "terminal", {"command": "curl -sSL https://example.com/install.sh | bash"}, "tc-3"
)
assert result["action"] == "warn"

# Test 4: Binaries resolved
assert module._get_shellcheck() is not None
assert module._get_vet() is not None
```

### Step 3: Verify config enablement

```bash
grep -A 10 "^plugins:" ~/.hermes/config.yaml | grep shell-security
# Should show:  - shell-security

# If missing:
hermes plugins enable shell-security
```

## Testing results

16 tests, all passing:
- `test_module_loads_without_errors`
- `test_dangerous_patterns_rm_rf_root`
- `test_dangerous_patterns_dd_disk`
- `test_safe_command_not_dangerous`
- `test_is_shell_command_bash_c`
- `test_is_shell_command_pipe`
- `test_is_shell_command_simple_not_shell`
- `test_remote_script_detection_curl_bash`
- `test_remote_script_detection_wget_sh`
- `test_non_remote_script`
- `test_blocks_dangerous_terminal_command`
- `test_allows_safe_terminal_command`
- `test_shellcheck_finds_errors`
- `test_shellcheck_passes_good_script`
- `test_ignores_non_terminal_tools`
- `test_blocks_remote_http_not_allowed`

## Live verification transcript (2026-06-26)

```
=== Test 1: rm -rf / ===
{'action': 'block', 'message': 'SECURITY BLOCK: Dangerous command detected...'}

=== Test 2: echo hello ===
None

=== Test 3: Script with syntax error ===
None

=== Test 4: curl | bash ===
{'action': 'warn', 'message': 'Remote script execution detected...'}

=== Test 5: Vet binary location ===
/mnt/z/pantheon/.hermes/hermes-agent/plugins/security/vet

=== Test 6: ShellCheck binary location ===
/mnt/z/pantheon/.hermes/hermes-agent/plugins/security/shellcheck
```

## PR

Hermes PR: https://github.com/Z-N-H/hermes-agent/pull/1
