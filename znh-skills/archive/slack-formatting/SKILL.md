---
name: slack-formatting
description: >
  Slack output formatting in Hermes — what the platform adapter supports,
  how Slack mrkdwn differs from standard markdown, Block Kit capabilities,
  and the gap between incoming Block Kit parsing and outgoing plain-text
  delivery. Use when the user asks about Slack message formatting, rich
  cards, Block Kit, or wants better visual output from Hermes in Slack.
triggers:
  - "slack format"
  - "slack block kit"
  - "slack formatting"
  - "better slack output"
  - "rich slack messages"
---

# Slack Formatting in Hermes

## Current Adapter Behavior

The Hermes Slack adapter (`gateway/platforms/slack.py`) sends messages via
`chat_postMessage` with:

- `text`: the message content
- `mrkdwn: True`
- Optional `thread_ts` for thread replies
- Optional `reply_broadcast` (first chunk only, if enabled)
- **Block Kit `blocks`** — when the content contains structural elements

Block Kit is **used for outgoing** messages when `_should_use_block_kit(content)`
detects headers, fenced code blocks, tables, dividers, or long text with bold
sub-headings. The adapter falls back to plain mrkdwn for simple messages.

## Slack mrkdwn Limitations

Slack mrkdwn is a subset of standard markdown:

| Feature | Slack mrkdwn | Standard markdown |
|---------|-------------|-------------------|
| Bold | `*text*` | `**text**` |
| Italic | `_text_` | `*text*` |
| Inline code | `` `code` `` | same |
| Code blocks | ` ```lang\ncode\n``` ` | same |
| Quotes | `> text` | same |
| Tables | **Not supported** | `\| col \| col \|` |
| Nested lists | Flaky beyond 2 levels | Works |
| Headers | **Not supported** | `# H1` etc. |

Tables render as broken text in Slack. Use ASCII tables inside triple-backtick
blocks instead.

## Block Kit (Not Currently Used for Outgoing)

Block Kit is Slack's JSON UI framework for rich message layouts:

- `section` — text with optional side images or fields
- `divider` — horizontal rules
- `header` — large bold text
- `image` — inline with alt text
- `button` — clickable actions
- `input` — dropdowns, date pickers, text inputs
- `context` — small metadata text

### The Gap

The adapter reads Block Kit from **incoming** messages (so the agent can see
what the user sent), but it never constructs Block Kit for **outgoing**
messages. To add Block Kit output, the adapter would need:

1. A `send_blocks()` method (or `blocks` parameter on `send()`)
2. A markdown → Block Kit JSON converter
3. Detection of when to use Block Kit vs. plain text

### Minimal Implementation Sketch

```python
# In SlackAdapter.send():
if metadata and metadata.get("use_blocks"):
    blocks = self._markdown_to_blocks(content)
    kwargs["blocks"] = blocks
    # When blocks are present, text becomes fallback for notifications
    kwargs["text"] = self._strip_markdown(content)[:300]
```

## User Preference

User prefers Block Kit-style rich formatting over plain mrkdwn for complex
responses (tables, structured data, multi-section layouts). When the user asks
about better Slack formatting, Block Kit is the right answer; plain mrkdwn
improvements are the fallback.

## Tool Progress / Tool-Use Chatter on Slack

By default, **Hermes disables tool-progress messages on Slack** (`tool_progress: off`)
because Slack cannot edit messages in-place — each progress line becomes a
permanent separate post. The built-in default lives in `gateway/display_config.py`:
`"slack": {**_TIER_MEDIUM, "tool_progress": "off"}`.

However, if the **global** `display.tool_progress` is set (e.g. `all`), it
overrides the platform default and Slack starts spamming separate "🛠️ terminal: …"
status messages for every tool call.

### Fix: per-platform override

```bash
hermes config set display.platforms.slack.tool_progress off
```

Or manually in `config.yaml`:

```yaml
display:
  platforms:
    slack:
      tool_progress: false
```

After changing, **restart the gateway** (`/restart` in chat, or
`hermes gateway restart`).

### Why this matters

- `all` — every tool call posts a separate Slack message (very noisy)
- `new` — only posts when the tool *name* changes (moderate noise)
- `off` — no separate progress messages; only the final response appears
- Slack has **no message editing**, so `cleanup_progress: true` has no effect

## Workarounds for Better Plain-Text Output

When Block Kit is not available:

1. **Never use markdown tables** — use ASCII tables inside code blocks
2. **Keep list nesting to 2 levels max** — Slack's parser gets flaky
3. **Separate explanatory text from code blocks** — don't mix markdown
   formatting inside ``` blocks
4. **Use bold + line breaks** instead of headers (`*Section Title*\n`)
5. **Break up wall-of-text** — shorter chunks with blank lines between ideas

## Related Files

- `plugins/platforms/slack/adapter.py` — SlackAdapter class
- `gateway/relay/adapter.py` — generic relay adapter (also no Block Kit)
- `gateway/platforms/base.py` — BasePlatformAdapter abstract methods

## Block Kit Rich Formatting

When the user explicitly asks for "rich Slack messages", "cards", "Block Kit", or
"better visual output", use the full Block Kit JSON framework.

**Block Kit outgoing support** is handled by `slack-block-kit-rich-formatting`.
Key capabilities:
- `section` blocks with fields for side-by-side data
- `divider` for visual separation
- `header` for large bold titles
- `image` with alt text
- `button` for interactive actions
- `context` for metadata footers

**Important constraint:** Hermes currently parses incoming Block Kit interactions
but does **not** generate outgoing Block Kit blocks automatically. To send Block Kit,
use the `send_message` tool with a JSON `blocks` payload.

**Send a rich message via `send_message`:**
```python
send_message(
    message="Summary here",
    target="slack:#channel-name",
    blocks=[
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Deployment Status", "emoji": True}
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": "*Environment:*\nProduction"},
                {"type": "mrkdwn", "text": "*Status:*\n✅ Healthy"}
            ]
        },
        {"type": "divider"},
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": "Triggered by Hermes Agent"}
            ]
        }
    ]
)
```

**Pitfall — `reply_broadcast` + thread mismatch:**
If a message is posted in a thread (`thread_ts` is set) but `reply_broadcast=True`
is not set, Block Kit sections that reference the channel context may fail to render.
Always verify the target is a channel (not a DM) before setting `reply_broadcast`.

**Validation payload** (send to yourself first):
```python
# Dry-run: send to a test channel or DM
send_message(
    message="Test",
    target="slack:@your_username",
    blocks=[...]
)
```

See `references/block-kit/example-payload.md` for a full Block Kit message example.
See `references/block-kit/send_message_tool_patch.md` for the patch that adds
`blocks` support to the `send_message` tool.
