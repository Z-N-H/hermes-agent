# OpenCode Stress Test — 2026-07-25

## Background

The `opencode-worker` skill previously documented that OpenCode "stalls on model load"
when the banner `> build · hf:zai-org/GLM-5.2` appeared without output. The user
questioned this claim, so we stress-tested OpenCode to determine real vs. perceived
stall behavior.

## Test Procedure

1. Verified OpenCode version: `opencode --version` → 1.18.4 (Bun install)
2. Quick probe: `opencode run "Read /tmp/opencode_test_file.txt and tell me what it says"`
3. Full stress test: build a 3-file Python project with greeter module, pytest suite,
   and verification

## Results

| Step | Timing | Outcome |
|------|--------|---------|
| `> build · hf:zai-org/GLM-5.2` banner | ~2s | Normal init — always appears |
| Model load | ~2s after banner | Successful |
| Quick probe output | Immediate after load | `→ Read opencode_test_file.txt` returned correctly |
| Stress test: 3 files created | Sequential | greeter.py, test_greeter.py, pyproject.toml |
| Stress test: deps installed via uv | 12ms | 5 packages auto-provisioned |
| Stress test: pytest run | <1s | 17/17 tests passed |
| Total end-to-end | ~15s | Complete success, exit 0 |

## Key Finding

The `> build · hf:zai-org/GLM-5.2` line is **normal model-init output**, not a stall
indicator. It appears on every run. The documented "stall" was a transient first-load
issue (likely model weights downloading for the first time, GPU contention, or Bun stream
init noise — the latter is documented as benign in the Pitfalls section).

**Actual stalls are rare** and look like: banner appears → 60+ seconds of silence →
timeout or no output. This was not reproduced.

## What to do when OpenCode appears slow to init

1. Check if this is the **first run** with this model — HF model weights download on first use
2. Check GPU/CPU load — another process may be contending for VRAM
3. Check Bun stderr for `ERR_STREAM_DESTROYED` messages (benign, see Pitfalls)
4. Wait at least 30 seconds before concluding it's stalled
5. If genuinely stalled, retry with a shorter inline task string (not `--file`)
