---
name: language-debuggers
description: "Language-specific debugging: Python (pdb + debugpy) and Node.js (node inspect + Chrome DevTools Protocol)."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [debugging, python, nodejs, pdb, debugpy, breakpoints, dap, post-mortem, cdp]
    related_skills: [systematic-debugging, plan, test-driven-development]
---

# Language Debuggers

When `print` / `console.log` isn't enough, use a real debugger. This skill covers Python and Node.js — pick the section for your language.

**General rule:** Start with the cheapest thing that works (`breakpoint()` in Python, `node inspect` in Node). Escalate to remote/headless debuggers only when the process is long-lived, the bug is in a child process, or you need IDE integration.

---

## Python — pdb + debugpy

### Three tools, picked by situation

| Tool | When |
|---|---|
| `breakpoint()` + pdb | Local, interactive, simplest. |
| `python -m pdb` | Launch an existing script under pdb with no source edits. |
| `debugpy` | Remote / headless / attach to already-running process. Talks DAP. |

### pdb quick reference

Inside any `(Pdb)` prompt:

| Command | Action |
|---|---|
| `n` | next line (step over) |
| `s` | step into |
| `r` | return from current function |
| `c` | continue |
| `b file:line` / `b func` | set breakpoint |
| `cl N` | clear breakpoint N |
| `l` / `ll` | list source around current line / full function |
| `w` | where (stack trace) |
| `u` / `d` | move up / down in the stack |
| `p expr` / `pp expr` | print / pretty-print |
| `display expr` | auto-print on every stop |
| `interact` | drop into full Python REPL in current scope (Ctrl+D to exit) |
| `!stmt` | execute arbitrary Python (assignments included) |
| `q` | quit |

### Recipes

**Local breakpoint (simplest):**
```python
def compute(x, y):
    result = some_helper(x)
    breakpoint()  # drops into pdb here
    return result + y
```
Remove `breakpoint()` before committing: `rg -n 'breakpoint\(\)' --type py`

**Launch under pdb (no source edits):**
```bash
python -m pdb path/to/script.py arg1 arg2
# (Pdb) b path/to/script.py:42
# (Pdb) c
```

**Debug a pytest test:**
```bash
scripts/run_tests.sh tests/foo_test.py::test_bar --pdb -p no:xdist
# xdist breaks pdb — always disable it
```

**Post-mortem on any exception:**
```python
import pdb, sys

try:
    run_the_thing()
except Exception:
    pdb.post_mortem(sys.exc_info()[2])
```

**Remote debug with debugpy (long-lived processes):**

Setup:
```bash
source /home/bb/hermes-agent/.venv/bin/activate
pip install debugpy
```

Pattern A — source-edit, process waits:
```python
import debugpy

debugpy.listen(("127.0.0.1", 5678))
debugpy.wait_for_client()
debugpy.breakpoint()
```

Pattern B — no source edit:
```bash
python -m debugpy --listen 127.0.0.1:5678 --wait-for-client your_script.py
```

Pattern C — attach to running PID:
```bash
python -m debugpy --listen 127.0.0.1:5678 --pid <pid>
```

Attach from VS Code / Cursor / Zed:
```json
{
  "name": "Attach to Hermes",
  "type": "debugpy",
  "request": "attach",
  "connect": { "host": "127.0.0.1", "port": 5678 }
}
```

**Agent-friendly alternative to debugpy: remote-pdb**
```bash
pip install remote-pdb
```
In code: `from remote_pdb import set_trace; set_trace(host="127.0.0.1", port=4444)`
Terminal: `nc 127.0.0.1 4444` → get a `(Pdb)` prompt exactly as if debugging locally.

`remote-pdb` is the cleanest agent-friendly choice when `debugpy`'s DAP is overkill.

### Common Python pitfalls

1. **pdb under pytest-xdist silently hangs.** Use `-p no:xdist` or `-n 0`.
2. **`breakpoint()` in CI hangs.** Never commit it. Add a pre-commit grep.
3. **`PYTHONBREAKPOINT=0` disables all breakpoints.** Check the env.
4. **Threads.** pdb only debugs the current thread. Use `debugpy` for multithreaded code.
5. **asyncio.** `await` inside pdb requires Python 3.13+ or `interact` mode tricks.
6. **`scripts/run_tests.sh` strips credentials.** If your bug depends on user config, debug with raw `pytest` first.
7. **Forking / multiprocessing.** pdb does not follow forks. Each child needs its own `breakpoint()`.

---

## Node.js — node inspect + CDP

### Two tools, pick one

| Tool | When |
|---|---|
| `node inspect` | Built-in, zero install, CLI REPL. Best for quick poking. |
| `ndb` / `chrome-remote-interface` | Scriptable from Node/Python. Best for automation, non-interactive, or collecting state across runs. |

### `node inspect` REPL quick reference

Launch paused on first line:
```bash
node inspect path/to/script.js
# or: node --inspect-brk $(which tsx) path/to/script.ts
```

| Command | Action |
|---|---|
| `c` / `cont` | continue |
| `n` / `next` | step over |
| `s` / `step` | step into |
| `o` / `out` | step out |
| `sb('file.js', 42)` | set breakpoint at file.js line 42 |
| `sb('functionName')` | break when function is called |
| `cb('file.js', 42)` | clear breakpoint |
| `bt` | backtrace (call stack) |
| `list(5)` | show 5 lines around current position |
| `repl` | drop into JS REPL in current scope (Ctrl+C to exit) |
| `exec expr` | evaluate expression once |
| `restart` / `kill` / `.exit` | restart / kill / quit |

### Attaching to a running process

```bash
kill -SIGUSR1 <pid>
curl -s http://127.0.0.1:9229/json/list | jq -r '.[0].webSocketDebuggerUrl'
node inspect ws://127.0.0.1:9229/<uuid>
```

Or start with inspector:
```bash
node --inspect script.js           # listen on 127.0.0.1:9229, keep running
node --inspect-brk script.js       # listen AND pause on first line
node --inspect=0.0.0.0:9230 script.js   # custom host:port
```

### Programmatic CDP (scripting from terminal)

For automation — set many breakpoints, capture scope state, script a repro:

```bash
npm i -g chrome-remote-interface
node --inspect-brk=9229 target.js &
```

Driver script (save as `/tmp/cdp-debug.js`):
```javascript
const CDP = require('chrome-remote-interface');
(async () => {
  const client = await CDP({ port: 9229 });
  const { Debugger, Runtime } = client;
  Debugger.paused(async ({ callFrames, reason }) => {
    const top = callFrames[0];
    console.log(`PAUSED: ${reason} @ ${top.url}:${top.location.lineNumber+1}`);
    for (const scope of top.scopeChain) {
      if (scope.type === 'local' || scope.type === 'closure') {
        const { result } = await Runtime.getProperties({
          objectId: scope.object.objectId, ownProperties: true
        });
        for (const p of result) {
          console.log(`  ${scope.type}.${p.name} =`, p.value?.value ?? p.value?.description);
        }
      }
    }
    await Debugger.resume();
  });
  await Runtime.enable(); await Debugger.enable();
  await Debugger.setBreakpointByUrl({ urlRegex: '.*app\\.tsx$', lineNumber: 119, columnNumber: 0 });
  await Runtime.runIfWaitingForDebugger();
})();
```

Run: `node /tmp/cdp-debug.js`

### Heap snapshots & CPU profiles (non-interactive)

Swap `Debugger` for `HeapProfiler` / `Profiler` in the CDP script:
```javascript
// CPU profile for 5 seconds
await client.Profiler.enable();
await client.Profiler.start();
await new Promise(r => setTimeout(r, 5000));
const { profile } = await client.Profiler.stop();
fs.writeFileSync('/tmp/cpu.cpuprofile', JSON.stringify(profile));

// Heap snapshot
await client.HeapProfiler.enable();
const chunks = [];
client.HeapProfiler.addHeapSnapshotChunk(({ chunk }) => chunks.push(chunk));
await client.HeapProfiler.takeHeapSnapshot({ reportProgress: false });
fs.writeFileSync('/tmp/heap.heapsnapshot', chunks.join(''));
```

### Common Node pitfalls

1. **Wrong line numbers in TS source.** Breakpoints hit emitted JS, not `.ts`. Use `dist/*.js` or enable sourcemaps (`node --enable-source-maps`).
2. **`--inspect` vs `--inspect-brk`.** `--inspect` doesn't pause; your script may race past the first breakpoint.
3. **Port collisions.** Default is `9229`. For multiple processes, pass `--inspect=0` (random port) and read actual URL from `/json/list`.
4. **Child processes.** `--inspect` on a parent does NOT inspect children. Use `NODE_OPTIONS='--inspect-brk'` to propagate.
5. **Background kills.** If you `Ctrl+C` out of `node inspect` while target is paused, target stays paused. `cont` first, or `kill` explicitly.
6. **Security.** `--inspect=0.0.0.0:9229` exposes arbitrary code execution. Always bind to `127.0.0.1` unless isolated.

---

## Language-agnostic verification checklist

After setting up a debug session, verify:
- [ ] Target is actually listening (curl the inspector endpoint for Node; `ss -tlnp | grep 5678` for Python)
- [ ] First breakpoint actually hits (if not, you likely missed `--inspect-brk` or are under xdist)
- [ ] Source listing at pause shows the right file (mismatch = sourcemap issue or wrong path)
- [ ] `where` / `w` / `bt` shows the expected call stack
- [ ] Post-debug cleanup: no stray `breakpoint()` / `set_trace()` / `debugpy.listen` in committed code
