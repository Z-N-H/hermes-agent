# Hermes Security Plugin: ShellCheck + vet Integration

Validates shell commands before execution using ShellCheck and vet. Hooks into `pre_tool_call` for `terminal` and `execute_code` tools.

## Plugin Location

```
plugins/security/
├── plugin.yaml              # Manifest (hooks: pre_tool_call)
├── __init__.py              # Validation logic
├── download_binaries.py     # Auto-downloads ShellCheck and vet on first use
├── .gitignore               # Excludes downloaded binaries from git
└── tests/
```

## Key Principle: Do Not Commit Binaries to Git

ShellCheck is ~15MB. Instead of committing it, the plugin downloads it on first use:

```python
def _get_shellcheck() -> str | None:
    plugin_dir = Path(__file__).parent
    local_binary = plugin_dir / "shellcheck"
    if local_binary.exists():
        return str(local_binary)
    found = shutil.which("shellcheck")
    if found:
        return found
    # Auto-download
    from .download_binaries import ensure_binaries
    sc, _ = ensure_binaries()
    return str(sc) if sc else None
```

`.gitignore`:
```
shellcheck
vet
*.tar.xz
```

## What It Blocks

| Pattern | Action |
|---------|--------|
| `rm -rf /` | Block |
| `dd if=... of=/dev/sd*` | Block |
| `mkfs.*` | Block |
| `curl ... \| bash` | Warn (recommend `vet URL`) |
| ShellCheck errors | Block (configurable) |
| ShellCheck warnings | Warn (configurable) |
| HTTP remote scripts | Block (only HTTPS allowed by default) |

## Hook Return Value

Returns a dict that Hermes interprets as a block/warn directive:

```python
{"action": "block", "message": "SECURITY BLOCK: ..."}
{"action": "warn", "message": "SECURITY WARNING: ..."}
```

Return `None` to allow execution.

## Configuration (Environment Variables)

| Variable | Default | Purpose |
|----------|---------|---------|
| `HERMES_SHELLCHECK_PATH` | auto-detect | Path to shellcheck binary |
| `HERMES_VET_PATH` | auto-detect | Path to vet binary |
| `HERMES_BLOCK_ON_ERROR` | `true` | Block if ShellCheck finds errors |
| `HERMES_WARN_ON_WARNING` | `true` | Warn if ShellCheck finds warnings |
| `HERMES_MAX_SCRIPT_SIZE` | `100000` | Skip scanning scripts larger than this |
| `HERMES_ALLOWED_SCHEMES` | `https` | Allowed URL schemes for remote scripts |

## Enabling the Plugin

```bash
hermes plugins enable security
```

## Testing

```bash
cd /mnt/z/pantheon/.hermes/hermes-agent
source venv/bin/activate
python -m pytest plugins/security/tests/ -v
```

16 tests cover: dangerous pattern detection, ShellCheck integration, remote script blocking, safe-command passthrough.
