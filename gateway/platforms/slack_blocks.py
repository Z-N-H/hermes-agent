"""Slack Block Kit helpers — convert markdown to rich Block Kit layouts."""

from __future__ import annotations

import re
from typing import Any, Dict, List


def markdown_to_slack_blocks(content: str) -> List[Dict[str, Any]]:
    """Convert markdown content into a list of Slack Block Kit blocks.

    Produces ``header``, ``section``, ``divider``, and ``context`` blocks
    for clean, readable Slack rendering.  Falls back to a single ``section``
    when the input is plain text.

    Rules
    -----
    * ``# Title`` → ``header`` block (plain_text, max 150 chars)
    * ``## Subtitle`` → ``section`` with bold text
    * ``---`` / ``***`` / ``___`` → ``divider`` block
    * ``\`\`\`lang\ncode\n\`\`\``` → ``section`` with mrkdwn code block
    * ``| table | rows |`` → ``section`` with mrkdwn code block
    * Bullet / numbered lists → ``section`` with mrkdwn
    * ``> quote`` → ``section`` with mrkdwn blockquote
    * Normal paragraphs → ``section`` with mrkdwn
    * Trailing metadata (e.g. ``— 3 min ago``) → ``context`` block
    """
    if not content:
        return []

    blocks: List[Dict[str, Any]] = []
    lines = content.split("\n")
    i = 0
    n = len(lines)

    # Buffer for accumulating plain text lines into a single section
    text_buffer: List[str] = []

    def _flush_text_buffer() -> None:
        nonlocal text_buffer
        if not text_buffer:
            return
        text = "\n".join(text_buffer).strip()
        text_buffer = []
        if not text:
            return
        # Escape backticks that would break mrkdwn inside a section
        # (fenced code blocks are handled separately)
        text = text.replace("```", "\u200b`\u200b`\u200b`\u200b")
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text[:3000]},
        })

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Header
        if re.match(r"^#{1,6}\s+", stripped):
            _flush_text_buffer()
            level = len(re.match(r"^(#+)", stripped).group(1))  # type: ignore[union-attr]
            header_text = re.sub(r"^#{1,6}\s+", "", stripped).strip()
            if header_text:
                if level == 1:
                    # Header block — plain_text only, 150 char max
                    blocks.append({
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": header_text[:150],
                            "emoji": True,
                        },
                    })
                else:
                    # Sub-header as bold section
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{header_text[:2970]}*",
                        },
                    })
            i += 1
            continue

        # Divider
        if re.match(r"^\s*([-=*_]){3,}\s*$", stripped):
            _flush_text_buffer()
            blocks.append({"type": "divider"})
            i += 1
            continue

        # Fenced code block
        if stripped.startswith("```"):
            _flush_text_buffer()
            lang = stripped[3:].strip()
            i += 1
            code_lines: List[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            code = "\n".join(code_lines)
            if code:
                prefix = f"```{lang}\n" if lang else "```\n"
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{prefix}{code[:2970]}\n```",
                    },
                })
            continue

        # Table (pipe-delimited lines)
        if stripped.startswith("|"):
            _flush_text_buffer()
            table_lines: List[str] = []
            while i < n and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].rstrip())
                i += 1
            table_text = "\n".join(table_lines)
            if table_text:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"```\n{table_text[:2970]}\n```",
                    },
                })
            continue

        # Horizontal rule inside text (rare but possible)
        if re.match(r"^\s*---\s*$", stripped):
            _flush_text_buffer()
            blocks.append({"type": "divider"})
            i += 1
            continue

        # Normal line — buffer it
        text_buffer.append(line)
        i += 1

    _flush_text_buffer()

    # Remove leading/trailing dividers for cleanliness
    while blocks and blocks[0].get("type") == "divider":
        blocks.pop(0)
    while blocks and blocks[-1].get("type") == "divider":
        blocks.pop()

    # Slack Block Kit limit: 50 blocks per message
    if len(blocks) > 50:
        # Keep first 49 blocks and add a context note
        blocks = blocks[:49]
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "_… (message truncated — too many blocks)_",
                }
            ],
        })

    return blocks


def blocks_to_payload(
    blocks: List[Dict[str, Any]],
    text_fallback: str = "",
) -> Dict[str, Any]:
    """Wrap Block Kit blocks into a ``chat.postMessage`` payload dict.

    Includes a ``text`` fallback for notifications / screen readers.
    """
    payload: Dict[str, Any] = {"blocks": blocks}
    if text_fallback:
        payload["text"] = text_fallback[:4000]
    else:
        # Derive plain-text fallback from the blocks
        fallback_parts: List[str] = []
        for blk in blocks:
            if blk.get("type") == "header":
                fallback_parts.append(blk.get("text", {}).get("text", ""))
            elif blk.get("type") == "section":
                txt = blk.get("text", {}).get("text", "")
                fallback_parts.append(txt)
        payload["text"] = "\n".join(fallback_parts)[:4000] or " "
    return payload
