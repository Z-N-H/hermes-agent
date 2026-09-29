---
name: vault-lookup-by-uid
description: Resolve an Obsidian note by its `uid` and get its full context — frontmatter, body, backlinks, board cards, and lineage. One command, instant.
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [obsidian, vault, lookup, uid, context]
    related_skills: [obsidian, vault-triage]
---

# Vault Lookup by UID

Every note in the vault has a `uid` in its frontmatter — an 8-character handle
like `k8MyXJVE`. Zack quotes these directly. When he does, that uid is the
whole instruction: resolve it and work out the rest yourself.

## Trigger Phrases

Any message containing a bare 8-character alphanumeric token alongside a verb:

- "review `k8MyXJVE`" / "look at `k8MyXJVE`" / "read `k8MyXJVE`"
- "what's `k8MyXJVE`" / "check `k8MyXJVE`" / "summarise `k8MyXJVE`"
- "`k8MyXJVE` needs updating" / "add a card for `k8MyXJVE`"

The uid may appear with or without backticks, in any case.

## Lookup — one command

```bash
python3 /mnt/z/pantheon/vault/ZNH/scripts/vault_lookup.py <UID>
```

That returns everything in one shot:

| Section | What it gives you |
|---|---|
| Lineage | client, project, type, status, folder |
| Frontmatter | every field on the note |
| Board cards | Kanban cards whose `note:` points at this note, with status/assignee/due |
| Referenced by | notes that wikilink to it, or quote its uid |
| Related (declared) | the note's own `related:` field |
| Note | the body |

Flags: `--no-body` for metadata only (cheap, use when you just need to know
what a note *is*), `--json` when you need to parse it.

**Do not** reach for `ccc search`, `search_files` or `read_file` to find a note
by uid. `ccc` runs off a semantic index that refreshes on a timer, so a note
written in the last minute is invisible to it — which is exactly when you're
most likely to be asked about one. `vault_lookup.py` reads a live index
(`.uid-index.json`, maintained by the trigger scanner) and falls back to a
direct scan on a miss, so it is never stale.

## Acting on the result

Once resolved, you have the note's real path. Normal file tools apply from
there — `read_file`, `write_file`, `patch`.

If the note has board cards, they are the work tracking for it: update the card
rather than writing status into the note body.

If a uid doesn't resolve, say so plainly. Don't guess at a similarly-named
note — a wrong note is worse than no note.

## Finding a note's uid

Going the other way (you have the note, you need the handle):

```bash
python3 -c "
import json
idx = json.load(open('/mnt/z/pantheon/vault/ZNH/.uid-index.json'))
print([k for k, v in idx.items() if 'Acme' in v])
"
```

Or just read the note — `uid:` is the first frontmatter key.

## Where uids come from

`scripts/vault_uid.py`, called by the trigger scanner whenever a file appears
or changes. Every note gets one within seconds of being written, regardless of
whether Obsidian is running.

Note that `id:` is a *different* key: TaskNotes cards carry a UUID there,
independent of `uid`. Never quote or match on `id:` — `uid:` is the only
address.
