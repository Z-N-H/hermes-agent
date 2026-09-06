"""Slack Block Kit helpers — convert markdown to rich Block Kit layouts."""

from __future__ import annotations

import re
from typing import Any, Dict, List


def markdown_to_slack_blocks(content: str) -> List[Dict[str, Any]]:
    """Convert markdown content into a list of Slack Block Kit blocks.

    Uses ``rich_text`` blocks for code (with native syntax highlighting via
    the ``language`` field) and ``section`` / ``header`` / ``divider`` for
    everything else.

    Rules
    -----
    * ``# Title`` → ``header`` block (plain_text, max 150 chars)
    * ``## Subtitle`` → ``section`` with bold text
    * ``---`` / ``***`` / ``___`` → ``divider`` block
    * ``\`\`\`lang\ncode\n\`\`\``` → ``section`` block with mrkdwn code block
      (rich_text is not supported by chat.postMessage API)
    * ``| table | rows |`` → ``section`` with mrkdwn code block
    * Bullet / numbered lists → ``section`` with mrkdwn
    * ``> quote`` → ``section`` with mrkdwn blockquote
    * Normal paragraphs → ``section`` with mrkdwn
    """
    if not content:
        return []

    blocks: List[Dict[str, Any]] = []
    lines = content.split("\n")
    i = 0
    n = len(lines)

    text_buffer: List[str] = []

    def _flush_text_buffer() -> None:
        nonlocal text_buffer
        if not text_buffer:
            return
        text = "\n".join(text_buffer).strip()
        text_buffer = []
        if not text:
            return
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
                    blocks.append({
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": header_text[:150],
                            "emoji": True,
                        },
                    })
                else:
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

        # Fenced code block → section with mrkdwn code block
        # Note: rich_text blocks are NOT supported by chat.postMessage API
        # (desktop/mobile apps only). We use standard section blocks with
        # mrkdwn code formatting instead.
        if stripped.startswith("```"):
            _flush_text_buffer()
            lang_match = re.match(r"^```(\w+)", stripped)
            language = lang_match.group(1) if lang_match else ""
            i += 1
            code_lines: List[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            code = "\n".join(code_lines)
            if code:
                lang_tag = f"{language}\n" if language else ""
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"```{lang_tag}{code}\n```",
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

        # Normal line — buffer it
        text_buffer.append(line)
        i += 1

    _flush_text_buffer()

    # Remove leading/trailing dividers
    while blocks and blocks[0].get("type") == "divider":
        blocks.pop(0)
    while blocks and blocks[-1].get("type") == "divider":
        blocks.pop()

    # Slack Block Kit limit: 50 blocks per message
    if len(blocks) > 50:
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
