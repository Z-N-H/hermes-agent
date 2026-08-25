---
name: social-media
description: "Social media operations: X/Twitter (xurl CLI) and YouTube content extraction."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [social-media, twitter, x, youtube, xurl, transcript, content]
---

# Social Media

Operate social platforms from the terminal. Covers X/Twitter posting and engagement via the official `xurl` CLI, and YouTube content extraction via transcript API.

---

## X / Twitter (`xurl`)

Official X developer platform CLI. All commands return JSON to stdout.

### Setup

```bash
pip install xurl
xurl auth
```

### Posting

```bash
xurl post "Hello world"                              # plain text
xurl post "Check this out" --media /path/to/img.jpg  # with media
xurl post "Replying" --reply-to 1234567890           # reply
xurl post "Quoting" --quote 1234567890               # quote tweet
```

### Search & Timeline

```bash
xurl search "llm inference" --limit 20               # search posts
xurl mentions                                        # your mentions
xurl timeline                                        # your timeline
xurl user-timeline elonmusk --limit 10               # specific user's posts
```

### Engagement

```bash
xurl like 1234567890
xurl repost 1234567890
xurl bookmark 1234567890
xurl follow elonmusk
xurl block spamaccount
```

### Direct Messages

```bash
xurl dm send elonmusk "Hello from Hermes"
xurl dm list                                         # conversation list
xurl dm show 9876543210                              # specific conversation
```

### Raw API Access

For endpoints not covered by shortcuts:

```bash
xurl api GET /2/tweets/1234567890
xurl api POST /2/tweets -d '{"text":"Hello"}'
```

### Multi-Account

```bash
xurl --app my-app post "Hello"        # use different app credentials
xurl --app brand-account post "Launch day!"
```

---

## YouTube Content Extraction

Extract transcripts and transform them into summaries, threads, or blog posts.

### Setup

```bash
uv pip install youtube-transcript-api
```

### Extract Transcript

```bash
python3 /path/to/fetch_transcript.py "https://youtube.com/watch?v=VIDEO_ID"
```

Supports any standard YouTube URL format: watch links, short links (youtu.be), shorts, embeds, live links, or raw 11-character video IDs.

### Content Transformations

- **Summary:** Extract key points and takeaways.
- **Thread:** Break into Twitter/X thread format (numbered, under 280 chars each).
- **Blog post:** Expand into a full article with headings and examples.
- **Chapters:** Identify natural breaks and create chapter timestamps.

---

## When to Use What

| Task | Tool |
|------|------|
| Post to X/Twitter | `xurl` |
| Search X posts | `xurl` |
| Send X DM | `xurl` |
| Extract YouTube transcript | `youtube-transcript-api` |
| Summarize a video | `youtube-transcript-api` + synthesis |

## Related Skills

- `humanizer` — For humanizing AI-generated social copy before posting.
