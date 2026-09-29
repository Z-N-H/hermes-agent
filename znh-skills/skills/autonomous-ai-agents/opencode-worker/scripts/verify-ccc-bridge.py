#!/usr/bin/env python3
"""Verify the ccc search bridge is healthy and reachable."""

import urllib.request, json, sys

BRIDGE = "http://127.0.0.1:8377"


def check():
    health = json.loads(urllib.request.urlopen(f"{BRIDGE}/health", timeout=5).read())
    search = json.loads(
        urllib.request.urlopen(f"{BRIDGE}/search?q=test&limit=1", timeout=10).read()
    )
    assert health.get("ok"), f"health failed: {health}"
    assert "results" in search, f"search failed: {search}"
    print(
        f"OK  bridge={BRIDGE} health={health['ok']} index={health.get('index_ready')} results={len(search['results'])}"
    )


if __name__ == "__main__":
    check()
