---
name: vault-tagging
description: The tag convention for every note and card in the ZNH Obsidian vault — client/<slug>, src/<source>, type tags, needs-triage — plus the check command. Load before writing or editing any `tags:` frontmatter in the vault.
platforms: [linux]
environments: [hermes]
metadata:
  hermes:
    tags: [obsidian, vault, tags, frontmatter, conventions]
    related_skills: [obsidian-vault-writes, granola-meeting-filing, zight-transcript-filing, vault-triage, tasknotes-board]
---

# Vault Tagging (ZNH)

One tag convention for everything under `/mnt/z/pantheon/vault/ZNH/`: meeting notes, transcripts, client docs, and Kanban cards. Notes and cards must agree, so "everything for Thankbox" is one tag filter, not three.

**Load this skill whenever you write or edit a `tags:` field in the vault**, alongside the source-specific filing skill (which says *what* to file) and `obsidian-vault-writes` (which covers *how* to write safely). If a filing skill's template disagrees with this skill about tags, this skill wins.

## The convention

| Tag | Means | Example |
|---|---|---|
| `client/<slug>` | The note or card belongs to this client | `client/thankbox`, `client/we-buy-any-house` |
| `src/<source>` | Where it came from (provenance) | `src/granola`, `src/zight`, `src/manual`, `src/pantheon` |
| `<type>` | What kind of note it is (one bare word) | `meeting`, `capture` |
| `needs-triage` | Client couldn't be confidently matched | — |
| `status/<state>` | Lifecycle of a client hub note | `status/active` |
| topic tags | Free-form, lowercase kebab-case | `seo`, `hreflang`, `landing-pages` |

### Client slug

`<slug>` is derived from the entry under `Clients/` — a folder (`Clients/We Buy Any House/`) or a top-level note (`Clients/Acme Corp.md`), never `Clients.md` — using the same rule `vault_board.py` uses for cards: lowercase, strip everything but `a-z0-9`, spaces and hyphens, join the first 4 words with `-`.

`We Buy Any House` → `we-buy-any-house` · `JR Pass` → `jr-pass` · `Neary-Hayes` → `neary-hayes` · `EduAdmin` → `eduadmin`

Never invent a slug. If the client isn't under `Clients/`, it isn't a client: use `needs-triage` and leave `client:` empty.

### Never

- A bare client slug: ~~`thankbox`~~ → `client/thankbox`
- The old hyphen form: ~~`client-thankbox`~~ → `client/thankbox`
- A non-client under `client/`: ~~`client/active`~~ → `status/active`; ~~`client/pantheon`~~ (Pantheon work is `client/neary-hayes`)
- A bare source word as provenance: ~~`granola`~~ on a Granola-filed note → `src/granola`. (A bare `granola` *topic* tag on a card that is *about* Granola is fine.)
- The same client in two forms on one file
- `#` prefixes, spaces or capitals in frontmatter tags

## Per note type

**Meeting note** (`Meetings/`, from `granola-meeting-filing`):
```yaml
source: granola
client: Thankbox
tags: [meeting, src/granola, client/thankbox]      # or [meeting, src/granola, needs-triage]
```

**Transcript** (`Transcripts/`, from `zight-transcript-filing`):
```yaml
source: zight
tags: [capture, src/zight, client/thankbox]        # or [capture, src/zight, needs-triage]
```

**Client doc** (anything under `Clients/<X>/`): `client/<slug>` plus topic tags. The client hub note (`Clients/<X>/<X>.md`) may add `status/<state>`.

**Kanban card** (`TaskNotes/Tasks/`): **don't put `client/` or `src/` in `--tags` at all.** `vault_board.py upsert` derives them from `--client` and `--source` and strips any you pass. Pass the real source:
```
vault_board.py upsert --title "..." --client "Thankbox" --source granola --tags "meeting-action,seo" ...
```
`--source` defaults to `manual`. Anything filed from a Granola meeting must pass `--source granola`; from a Zight capture, `--source zight`. Otherwise the card is mislabelled `src/manual`.

## Check before you finish

After writing or editing tags, run the checker. It must exit 0:
```
uv run --no-project /mnt/z/pantheon/vault/ZNH/scripts/vault_tags.py check
```
It lists every file that breaks the convention, plus any `client/` tag that doesn't name a real client (those need a human decision; don't guess).

`vault_tags.py migrate` (dry run) / `migrate --write` rewrites the mechanical cases: bare and hyphen client slugs, `client/active`, and bare source tags that match the note's own `source:`. Use it for repairs, never as a substitute for tagging correctly in the first place.
