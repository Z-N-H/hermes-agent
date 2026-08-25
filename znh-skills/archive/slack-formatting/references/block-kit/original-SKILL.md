---
name: slack-block-kit-rich-formatting
description: |
  Enrich Hermes Slack platform adapter output with Slack Block Kit structured
  layouts (headers, sections, dividers, code blocks, tables). Auto-detects
  structural markdown content and routes to Block Kit, falling back to plain
  mrkdwn for simple messages.
trigger: |
  When working on Hermes Slack gateway output, formatting Slack messages,
  improving Slack readability, or adding rich layouts to the Slack adapter.
---

# Slack Block Kit Rich Formatting

## What this does

Converts Hermes assistant markdown output into Slack Block Kit ``blocks`` arrays
for significantly better readability in Slack channels and threads.  Simple
text continues to use plain mrkdwn; structured content (headers, code blocks,
tables, dividers) gets rendered as rich Block Kit cards.

## When to use

| Use Block Kit | Keep plain mrkdwn |
|---------------|-------------------|
| Has `# Title` headers | Short replies under 80 chars |
| Has ```` ``` ```` code blocks | Plain sentences |
| Has pipe tables `\| a \| b \|` | Single-line status |
| Has `---` dividers | Emoji-only reactions |
| Long structured content (>1200 chars) | Quick confirmations |

## Architecture

Two-file change on the **gateway adapter** plus a third file for the **standalone tool path**:

1. **New module** ``gateway/platforms/slack_blocks.py``
   - ``markdown_to_slack_blocks(content: str) -> List[Dict]`` — parses markdown
     into ``header``, ``section``, ``divider``, ``context`` blocks
   - ``blocks_to_payload(blocks, text_fallback) -> Dict`` — wraps blocks with
     a ``text`` fallback for notifications and screen readers

2. **Modified adapter** ``gateway/platforms/slack.py``
   - ``_should_use_block_kit(content) -> bool`` — structural marker detection
   - ``_send_blocks(chat_id, content, thread_ts, metadata)`` — Block Kit send
     path with plain-text fallback on any error
   - ``send()`` — router: checks ``_should_use_block_kit`` then dispatches

3. **Modified tool** ``tools/send_message_tool.py`` *(commonly missed)*
   - The ``send_message`` tool has its own ``_send_slack()`` helper that
     directly calls ``chat.postMessage`` via aiohttp, bypassing the gateway
     adapter entirely.  If you only patch the adapter, ``send_message``
     messages stay flat.  The tool must import ``slack_blocks`` and
     duplicate the ``_should_use_block_kit`` + Block Kit payload logic.
   - See ``references/send_message_tool_patch.md`` for the exact patch.

## Detection criteria (`_should_use_block_kit`)

```python
# True if any structural marker present
has_header   = bool(re.search(r"^#{1,6}\s+", content, re.MULTILINE))
has_code     = "```" in content
has_table    = bool(re.search(r"^\s*\|[^|]+\|", content, re.MULTILINE))
has_divider  = bool(re.search(r"^\s*([-=*_]){3,}\s*$", content, re.MULTILINE))

# OR long text with bold sub-headings
if len(content) > 1200:
    has_bold_header = bool(re.search(r"^\*\*.+\*\*$", content, re.MULTILINE))
```

## Conversion rules

| Markdown | Block Kit block |
|----------|-----------------|
| `# Title` | ``header`` (plain_text, 150 char max) |
| `## Subtitle` | ``section`` with bold mrkdwn |
| `---` / `***` | ``divider`` |
| ```` ```lang\ncode\n``` ```` | ``rich_text`` block with ``rich_text_preformatted`` + ``language`` field (native Slack syntax highlighting) |
| `\| table \| rows \|` | ``section`` with mrkdwn code block |
| `> quote` | ``section`` with mrkdwn blockquote |
| Normal paragraphs | ``section`` with mrkdwn |
| Trailing metadata | ``context`` block |

## Fallback strategy

If Block Kit parsing fails or the Slack API rejects the ``blocks`` payload:

1. Log the error
2. **Directly** call ``chat_postMessage`` with plain mrkdwn text
3. Never recurse back into ``self.send()`` (avoids infinite Block Kit retry loop)

## Limits enforced

- **50 blocks max** per message — truncate with a trailing ``context`` note
- **3000 chars** per ``section`` ``text`` field
- **4000 chars** for the ``text`` fallback
- **150 chars** for ``header`` plain_text

## Testing the change

After committing to ``znh/custom``:

1. Restart the gateway with ``pantheon launch hermes-gateway`` (NOT ``hermes gateway run`` — the Pantheon launcher ensures integration)
2. Trigger a structured response with headers/code
3. Check Slack — should see clean sections instead of wall-of-text

## Related files

- ``gateway/platforms/slack.py`` — adapter (router + send path)
- ``gateway/platforms/slack_blocks.py`` — converter module
- ``references/slack-block-kit-payloads.md`` — example payloads

## Pitfalls

- **Restart method**: Always use ``pantheon launch hermes-gateway`` to restart
  the gateway after Block Kit changes.  Using ``hermes gateway run`` directly
  bypasses Pantheon integration.
- **Do NOT** put explanatory text inside code blocks when writing messages —
  the converter treats everything inside ```` ``` ```` as code.
- **Do NOT** call ``self.send()`` from the Block Kit fallback — causes
  recursion back into Block Kit detection.  Call ``chat_postMessage`` directly.
- Block Kit ``header`` blocks require ``plain_text``, not ``mrkdwn`` —
  no inline formatting in headers.
- Slack notifications show the ``text`` fallback, not the blocks — always
  include a meaningful fallback.
- **``.pyc`` bytecode caching**: After editing any `.py` file in a running
  Hermes process, stale ``__pycache__/*.pyc`` files may prevent the new code
  from loading.  Either restart the gateway or clear the cache:
  ``rm -f tools/__pycache__/send_message_tool.cpython-*.pyc``.
- **Tool path loses header blocks**: In ``_send_to_platform``,
  ``slack_adapter.format_message()`` runs *before* the message reaches
  ``_send_slack()``, converting ``# Title`` to ``*Title*``.  The tool's
  Block Kit path therefore sees bold text rather than headers and renders
  them as ``section`` blocks instead of ``header`` blocks.  Code blocks,
  tables, and dividers survive formatting intact and still trigger Block Kit.
  To get full ``header`` blocks from the tool path, run Block Kit on the
  raw markdown before ``format_message()`` touches it.
