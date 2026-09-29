#!/usr/bin/env python3
"""Persistent Hermes worker that eliminates interpreter cold-start.

The worker stays alive between requests, keeping the Python interpreter
warm.  It accepts JSON requests on stdin and streams JSON responses on
stdout.  Each request still spawns ``hermes chat`` (Hermes is one-shot),
but the worker process itself is persistent, cutting ~1–2 s of interpreter
startup per message.

Usage (from Python)::

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "hermes_worker.py",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    proc.stdin.write(json.dumps({"prompt": "hi"}).encode() + b"\n")
    await proc.stdin.drain()
    async for line in proc.stdout:
        msg = json.loads(line)
        if msg["type"] == "chunk":
            print(msg["data"], end="")
        elif msg["type"] == "done":
            break
"""

import asyncio
import json
import sys


async def run_hermes(prompt: str, max_turns: int = 3, session_id: str | None = None):
    """Run ``hermes chat`` and stream stdout chunks as JSON lines."""
    cmd = ["hermes", "chat", "-q", prompt, "-Q", "--max-turns", str(max_turns)]
    if session_id:
        cmd.extend(["--resume", session_id])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Stream stdout chunks in real-time
    chunks = []
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        chunk = line.decode("utf-8", errors="replace")
        chunks.append(chunk)
        # Emit chunk immediately for real-time streaming
        print(json.dumps({"type": "chunk", "data": chunk}), flush=True)

    # Wait for process to finish and capture stderr
    await proc.wait()
    stderr = (await proc.stderr.read()).decode("utf-8", errors="replace")

    # Emit completion with full metadata
    print(
        json.dumps({
            "type": "done",
            "stdout": "".join(chunks),
            "stderr": stderr,
            "returncode": proc.returncode,
        }),
        flush=True,
    )


async def main():
    loop = asyncio.get_event_loop()
    # Pre-warm: run a trivial hermes command so the OS caches the binary
    # and the interpreter warms up import paths.
    warmup = await asyncio.create_subprocess_exec(
        "hermes",
        "--version",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await warmup.wait()

    # Read JSON requests from stdin, one per line
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        try:
            req = json.loads(line.strip())
        except json.JSONDecodeError:
            continue
        await run_hermes(
            prompt=req["prompt"],
            max_turns=req.get("max_turns", 3),
            session_id=req.get("session_id"),
        )


if __name__ == "__main__":
    asyncio.run(main())
