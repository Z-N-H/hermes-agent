---
name: obsidian-cli
description: Use when interacting with Obsidian vaults via the Obsidian CLI to read, create, search, manage notes, tasks, properties, backlinks, and tags from the command line. Also use when developing or debugging Obsidian plugins and themes — reloading plugins, running JavaScript, capturing errors, taking screenshots, and inspecting the DOM. Requires Obsidian to be open.
---

# Obsidian CLI

Use the `obsidian` CLI to interact with a running Obsidian instance. Requires Obsidian to be open.

## Help & Docs
Run `obsidian help` to see all available commands. Full docs: https://help.obsidian.md/cli

## Syntax
**Parameters** take a value with `=`. Quote values with spaces:
```bash
obsidian create name="My Note" content="Hello world"
```
**Flags** are boolean switches with no value:
```bash
obsidian create name="My Note" silent overwrite
```
For multiline content use `\n` for newline and `\t` for tab.

## File Targeting
Many commands accept `file` or `path` to target a file. Without either, the active file is used.
- `file=` — resolves like a wikilink (name only, no path or extension needed)
- `path=` — exact path from vault root, e.g. `folder/note.md`

## Vault Targeting
Commands target the most recently focused vault by default. Use `vault=` as the first parameter to target a specific vault:
```bash
obsidian vault="My Vault" search query="test"
```

## Common Patterns
```bash
obsidian read file="My Note"
obsidian create name="New Note" content="# Hello" template="Template" silent
obsidian append file="My Note" content="New line"
obsidian search query="search term" limit=10
obsidian daily:read
obsidian daily:append content="- [ ] New task"
obsidian property:set name="status" value="done" file="My Note"
obsidian tasks daily todo
obsidian tags sort=count counts
obsidian backlinks file="My Note"
```

Use `--copy` on any command to copy output to clipboard. Use `silent` to prevent files from opening. Use `total` on list commands to get a count.

## Plugin Development

### Develop/Test Cycle
After making code changes to a plugin or theme:
1. **Reload** the plugin to pick up changes:
```bash
obsidian plugin:reload id=my-plugin
```
2. **Check for errors**:
```bash
obsidian dev:errors
```
3. **Verify visually** with a screenshot or DOM inspection:
```bash
obsidian dev:screenshot path=screenshot.png
obsidian dev:dom selector=".workspace-leaf" text
```
4. **Check console output**:
```bash
obsidian dev:console level=error
```

### Additional Developer Commands
Run JavaScript in the app context:
```bash
obsidian eval code="app.vault.getFiles().length"
```
Inspect CSS values:
```bash
obsidian dev:css selector=".workspace-leaf" prop=background-color
```
Toggle mobile emulation:
```bash
obsidian dev:mobile on
```
Run `obsidian help` to see additional developer commands including CDP and debugger controls.

## Common Pitfalls
- Obsidian **must be running** for the CLI to work — commands will fail with a connection error otherwise
- Use `silent` flag to prevent notes from opening in the UI during batch operations
- `vault=` parameter must be the first parameter if used