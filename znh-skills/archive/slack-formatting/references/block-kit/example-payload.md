# Example Block Kit payload from the znh/custom Slack adapter

This reference shows what the `slack_blocks.py` converter produces for a
structured assistant response.  Use it to sanity-check converter output.

## Input markdown

```markdown
# Analysis complete

## Summary

The TPS fix is working across all token types.

```python
# TPS improvements:
- reasoning chunks (fixed)
- suppressed text during tool calls (fixed)
- tool call JSON accumulation (fixed)
```

---

| Metric | Before | After |
|--------|--------|-------|
| Delay | ~40s | ~35s |
| Streaming | buffered | line-by-line |

> Restart Hermes to load the patched modules.
```

## Output blocks array

```json
[
  {
    "type": "header",
    "text": {
      "type": "plain_text",
      "text": "Analysis complete",
      "emoji": true
    }
  },
  {
    "type": "section",
    "text": {
      "type": "mrkdwn",
      "text": "*Summary*"
    }
  },
  {
    "type": "section",
    "text": {
      "type": "mrkdwn",
      "text": "The TPS fix is working across all token types."
    }
  },
  {
    "type": "rich_text",
    "elements": [
      {
        "type": "rich_text_preformatted",
        "language": "python",
        "elements": [
          {
            "type": "text",
            "text": "# TPS improvements:\n- reasoning chunks (fixed)\n- suppressed text during tool calls (fixed)\n- tool call JSON accumulation (fixed)"
          }
        ]
      }
    ]
  },
  {
    "type": "divider"
  },
  {
    "type": "section",
    "text": {
      "type": "mrkdwn",
      "text": "```\n| Metric | Before | After |\n|--------|--------|-------|\n| Delay | ~40s | ~35s |\n| Streaming | buffered | line-by-line |\n```"
    }
  },
  {
    "type": "section",
    "text": {
      "type": "mrkdwn",
      "text": "> Restart Hermes to load the patched modules."
    }
  }
]
```

## Payload wrapper

```json
{
  "channel": "C1234567890",
  "text": "Analysis complete\n*Summary*\nThe TPS fix is working across all token types.\nTPS improvements:\n- reasoning chunks (fixed)\n- suppressed text during tool calls (fixed)\n- tool call JSON accumulation (fixed)\nMetric | Before | After\nDelay | ~40s | ~35s\nStreaming | buffered | line-by-line\nRestart Hermes to load the patched modules.",
  "blocks": [ /* ... from above ... */ ],
  "thread_ts": "1234567890.123456"
}
```

## Key design notes

- Code blocks use `rich_text` → `rich_text_preformatted` with the `language`
  field (added by Slack in March 2026).  Slack renders syntax highlighting
  server-side — no Shiki or client JS required.
- The `text` field is required for notifications, search, and screen readers.
  It is a plain-text concatenation of the block content.
- Tables are rendered inside mrkdwn code blocks — Slack has no native table
  block, so monospace formatting is the cleanest fallback.
- The `header` block uses `plain_text` (Slack restriction), not `mrkdwn`.
