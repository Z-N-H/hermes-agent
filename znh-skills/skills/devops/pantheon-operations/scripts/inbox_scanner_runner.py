#!/usr/bin/env python3
"""Inbox scanner runner — periodic inbox processing with Slack notification.

Runs as a no_agent=true Hermes cron job (every 30m). Two phases:

1. Data collection — scan Inbox/,
   report which notes need Hermes and why.
2. Agent dispatch — if there's work,
   call `hermes chat -q` with the inbox
   context, the vault-triage skill, and
   Slack Block Kit templates.

Replaces the old inbox-scanner Hermes cron
that was removed when vault-librarian took
over mechanical work. This provides the LLM
layer vault-librarian can't: Kanban cards,
ClickUp tasks, Slack summaries.

Only Python stdlib + subprocess to hermes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VAULT = Path(
    os.environ.get(
        "VAULT_PATH",
        "/mnt/z/pantheon/vault/ZNH",
    )
)
HERMES = os.environ.get(
    "HERMES_BIN",
    "/home/znh/.local/bin/hermes",
)
HERMES_HOME = os.environ.get(
    "HERMES_HOME",
    "/mnt/z/pantheon/.hermes",
)

INBOX = VAULT / "Inbox"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_frontmatter(path: Path) -> dict[str, str]:
    """Extract frontmatter keys as a flat dict."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    result = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def scan_inbox() -> dict:
    """Classify inbox notes into buckets."""
    buckets = {
        "untriaged": [],  # no triage state, needs Hermes
        "failed": [],  # triage exited non-zero previously
        "parked": [],  # waiting on user
        "done": [],  # ready to file out
        "discarded": [],  # ready to archive
        "unreadable": [],  # can't read
    }
    if not INBOX.is_dir():
        return buckets

    for path in sorted(INBOX.glob("*.md")):
        if path.name.startswith("."):
            continue
        fm = read_frontmatter(path)
        triage = fm.get("triage", "").strip().lower()
        status = fm.get("status", "").strip().lower()
        title = fm.get("title") or path.stem
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        )
        uid = fm.get("uid", "")
        entry = {
            "path": str(path.relative_to(VAULT)),
            "title": title,
            "uid": uid,
            "mtime": mtime,
            "triage": triage,
        }

        if triage in ("parked",):
            buckets["parked"].append(entry)
        elif triage in ("done",):
            buckets["done"].append(entry)
        elif triage in ("discarded",):
            buckets["discarded"].append(entry)
        elif not triage:
            # Also check legacy status: keys
            if status in ("processed", "draft", "archived"):
                # Already triaged under old scheme
                buckets[
                    "done"
                    if status == "processed"
                    else "parked"
                    if status == "draft"
                    else "discarded"
                ].append(entry)
            else:
                buckets["untriaged"].append(entry)
        else:
            buckets["untriaged"].append(entry)

    return buckets


def build_prompt(buckets: dict) -> str:
    """Build the prompt for hermes chat -q."""
    sections = []
    total = sum(len(v) for v in buckets.values())

    sections.append(
        "You are the inbox processor. Your job: read each note below, classify "
        "it using the vault-triage skill, act on it (card, file, answer, park), "
        "and report back.\n"
    )
    sections.append(f"Scan time: {_now_iso()}")
    sections.append(f"Inbox contains {total} notes needing attention.\n")

    for label, items in [
        ("Untriaged — need classification", "untriaged"),
        ("Previously failed triage — retry", "failed"),
        ("Done — ready to file out of Inbox", "done"),
        ("Discarded — ready to archive", "discarded"),
        ("Parked — waiting on user", "parked"),
    ]:
        entries = buckets[items]
        if not entries:
            continue
        sections.append(f"## {label} ({len(entries)})")
        for e in entries:
            sections.append(
                f"- `{e['path']}` — {e['title']} (uid: `{e['uid'] or 'none'}`, modified: {e['mtime']})"
            )

    sections.append(
        "\n## Instructions\n"
        "1. Read each untriaged note fully. Follow the vault-triage skill.\n"
        "2. For each note: classify → act → stamp triage state.\n"
        "3. File done notes out of Inbox to their destination folder.\n"
        "4. Park ambiguous notes and Slack Zack with your question.\n"
        "5. After processing, send a single Slack Block Kit summary:\n"
        "   - What was classified, filed, carded, parked\n"
        "   - What needs Zack's attention\n"
        "   - What failed and why\n\n"
        "Use send_message with a blocks array for the Slack message.\n"
        "Keep the summary concise — Zack reads it on mobile."
    )

    return "\n".join(sections)


def _hermes_env() -> dict:
    return {
        **os.environ,
        "HERMES_HOME": HERMES_HOME,
        "HOME": os.environ.get("HOME", "/home/znh"),
        "PATH": os.path.expanduser("~/.local/bin") + ":" + os.environ.get("PATH", ""),
    }


def dispatch_hermes(prompt: str) -> None:
    """Fire-and-forget: kick off hermes chat -q in the background and return.

    The hermes session processes notes (classify, card, file, Slack) on its
    own. The cron job must not wait for it — the scheduler kills scripts that
    run longer than 120s, and hermes can take several minutes per batch.
    """
    try:
        subprocess.Popen(
            [
                HERMES,
                "chat",
                "-Q",
                "-q",
                prompt,
                "-t",
                "hermes-cli,opencode,mcp-pantheon",
                "--skills",
                "vault-triage,obsidian,vault-lookup-by-uid",
                "--source",
                "cron",
            ],
            env=_hermes_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        print(f"[INBOX-SCANNER] hermes not found at {HERMES}", file=sys.stderr)


def main() -> int:
    buckets = scan_inbox()
    actionable = (
        len(buckets["untriaged"])
        + len(buckets["failed"])
        + len(buckets["done"])
        + len(buckets["discarded"])
    )

    if actionable == 0:
        # Nothing to do — exit silently.
        # With no_agent=true, empty stdout means no delivery.
        return 0

    prompt = build_prompt(buckets)
    dispatch_hermes(prompt)
    return 0  # script succeeds; hermes runs in background


if __name__ == "__main__":
    sys.exit(main())
