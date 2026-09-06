---
name: productivity-integrations
description: "External productivity tool integrations — email, documents, spreadsheets, databases, and calendar."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [productivity, airtable, google, gmail, sheets, notion, teams, email]
---

# Productivity Integrations

## Overview

This umbrella covers external SaaS and productivity tool integrations available from
the terminal: Airtable (database), Google Workspace (Gmail, Calendar, Drive, Docs,
Sheets), Notion (pages and databases), Microsoft Teams (meeting pipeline), and
Himalaya (terminal email).

## 1. Airtable

REST API for records CRUD, filters, and upserts.

```bash
# List records
curl "https://api.airtable.com/v0/<base>/<table>" -H "Authorization: Bearer $AIRTABLE_API_KEY"

# Create a record
curl -X POST "https://api.airtable.com/v0/<base>/<table>" \
  -H "Authorization: Bearer $AIRTABLE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"fields": {"Name": "Test", "Status": "Active"}}'
```

Requires `AIRTABLE_API_KEY` and `AIRTABLE_BASE_ID` environment variables.

## 2. Google Workspace (gws CLI)

Terminal interface to Gmail, Calendar, Drive, Docs, and Sheets.

```bash
# Gmail search
gws gmail search "from:boss@company.com after:2026/01/01"

# Calendar list
gws calendar list --today

# Drive upload
gws drive upload file.pdf --folder "Reports"

# Sheets read
gws sheets read <spreadsheet_id> --range "Sheet1!A1:C10"
```

**Setup:** Run `gws auth` to authenticate via OAuth. Credentials are stored in
`~/.config/gws/`.

**Scripts:**
- `references/google-workspace/google_api.py` — Low-level Google API wrapper
- `references/google-workspace/gws_bridge.py` — Bridge between Hermes and gws
- `references/google-workspace/setup.py` — Automated setup script

## 3. Notion

Pages, databases, and markdown import/export via the Notion API + `ntn` CLI.

```bash
# List databases
ntn database list

# Query a database
ntn database query <database_id>

# Create a page
ntn page create --parent <parent_id> --title "New Note" --content "Body text"
```

**Block types:** See `references/notion/block-types.md` for the full supported block
list and JSON schema.

## 4. Teams Meeting Pipeline

Operate the Teams meeting summary pipeline via Hermes CLI.

```bash
# Start a meeting recording pipeline
hermes teams meeting start --name "Weekly Standup"

# Generate summary
hermes teams meeting summarize --id <meeting_id>

# List past meetings
hermes teams meeting list
```

## 5. Himalaya

Terminal IMAP/SMTP email client.

```bash
# List folders
himalaya folder list

# List messages in inbox
himalaya message list --folder INBOX

# Read a message
himalaya message read <uid>

# Compose and send
himalaya message write --to "user@example.com" --subject "Hello" --body "World"
```

**Setup:** Configure `~/.config/himalaya/config.toml` with IMAP/SMTP server details.

See `references/himalaya/configuration.md` for the full TOML config reference.
See `references/himalaya/message-composition.md` for templates and attachment handling.
