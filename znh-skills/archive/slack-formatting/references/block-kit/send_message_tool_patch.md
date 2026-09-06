# Patching `send_message_tool.py` for Block Kit support

**Problem**: The `send_message` tool's `_send_slack()` helper directly calls
`chat.postMessage` with plain `{"text": message, "mrkdwn": True}`.  It never
uses the gateway adapter, so even when `slack.py` has Block Kit routing,
messages sent via the tool render as flat text.

**Solution**: Add conditional Block Kit conversion inside `_send_slack()`.

---

## Step 1 — Top-of-file imports

Add near the top of `tools/send_message_tool.py` (before `logger =`):

```python
# Slack Block Kit support for rich message formatting
_try_slack_blocks = False
markdown_to_slack_blocks = None  # type: ignore
blocks_to_payload = None  # type: ignore
try:
    from gateway.platforms.slack_blocks import markdown_to_slack_blocks, blocks_to_payload  # noqa: F811
    _try_slack_blocks = True
except Exception:
    pass


def _should_use_block_kit(content: str) -> bool:
    """Return True when the content benefits from Block Kit layout."""
    if not content or len(content) < 80:
        return False
    has_header = bool(re.search(r"^#{1,6}\s+", content, re.MULTILINE))
    has_code = "```" in content
    has_table = bool(re.search(r"^\s*\|[^|]+\|", content, re.MULTILINE))
    has_divider = bool(re.search(r"^\s*([-=*_]){3,}\s*$", content, re.MULTILINE))
    structural = has_header or has_code or has_table or has_divider
    if structural:
        return True
    if len(content) > 1200:
        has_bold_header = bool(re.search(r"^\*\*.+\*\*$", content, re.MULTILINE))
        if has_bold_header:
            return True
    return False
```

The `None` defaults + `# noqa: F811` keep Pyright happy when the import
fails (e.g. in a standalone context without the full gateway).

---

## Step 2 — Modify `_send_slack()`

Replace the old `_send_slack` body with one that decides between Block Kit
and plain mrkdwn **before** calling `chat.postMessage`:

```python
async def _send_slack(token, chat_id, message, thread_ts=None):
    """Send via Slack Web API.

    Uses Block Kit rich layout when the message contains structural elements
    (headers, code blocks, tables, dividers) and falls back to plain mrkdwn
    for simple messages or when Block Kit conversion fails.
    """
    try:
        import aiohttp
    except ImportError:
        return {"error": "aiohttp not installed. Run: pip install aiohttp"}
    try:
        from gateway.platforms.base import resolve_proxy_url, proxy_kwargs_for_aiohttp
        _proxy = resolve_proxy_url()
        _sess_kw, _req_kw = proxy_kwargs_for_aiohttp(_proxy)
        url = "https://slack.com/api/chat.postMessage"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        use_blocks = _try_slack_blocks and _should_use_block_kit(message)
        payload: dict = {"channel": chat_id, "text": message}
        if thread_ts:
            payload["thread_ts"] = thread_ts

        if use_blocks and markdown_to_slack_blocks and blocks_to_payload:
            try:
                blocks = markdown_to_slack_blocks(message)
                if blocks:
                    blocks_payload = blocks_to_payload(blocks, text_fallback=message[:4000])
                    payload["text"] = blocks_payload["text"]
                    payload["blocks"] = blocks_payload["blocks"]
                else:
                    payload["text"] = message
                    payload["mrkdwn"] = True
            except Exception:
                logger.debug("Block Kit conversion failed, falling back to plain text", exc_info=True)
                payload["text"] = message
                payload["mrkdwn"] = True
        else:
            payload["text"] = message
            payload["mrkdwn"] = True

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), **_sess_kw) as session:
            async with session.post(url, headers=headers, json=payload, **_req_kw) as resp:
                data = await resp.json()
                if data.get("ok"):
                    return {"success": True, "platform": "slack", "chat_id": chat_id, "message_id": data.get("ts")}
                return _error(f"Slack API error: {data.get('error', 'unknown')}")
    except Exception as e:
        return _error(f"Slack send failed: {e}")
```

---

## Key design notes

- The tool path is **standalone** — it runs inside the agent process, not the
gateway process, so it cannot call `adapter.send()`.
- The `_should_use_block_kit` logic is intentionally duplicated from the
adapter so the tool is self-contained and does not depend on a running gateway.
- The `blocks_to_payload` call sets the `text` fallback (required for
notifications and screen readers) and wraps the blocks array.
- If Block Kit conversion throws, the function silently falls back to plain
mrkdwn — the user still gets their message.
