# LSP Configuration for Pantheon Monorepo

> Produced 2026-07-28 from a live project-stack audit of 15+ Pantheon projects.
> Use this to decide which LSP servers to enable in `opencode.json`.

## Project Stack Summary

| Project | Languages | Description |
|---------|-----------|-------------|
| **purple-phoenix** (Pantheon core) | Python (uv, ruff, pytest), TOML, YAML, JSON | Local dev env manager for AI agents |
| **topaz-thoth** (Nabu blog) | Python (litellm, agno, fastapi, playwright), TOML | Automated blog generation |
| **purple-odin** | TypeScript (Cloudflare Workers, wrangler), Python, JSON | Cloudflare tools and workers |
| **scarlet-minotaur** | Python (marimo, polars, plotly), TOML | Gift card keyword research notebooks |
| **scarlet-anansi** | Python (marimo, polars, httpx), TOML | SERP journey comparison research |
| **cobalt-fenrir** | Python (marimo, polars, httpx), TOML | Same project as scarlet-anansi variant |
| **emerald-phoenix** | Python, TOML | Blog/content generation |
| **cerulean-susanoo** | HTML/CSS (Tailwind, DaisyUI wireframes), Python | Eduadmin feature wireframes |
| **indigo-griffin** | HTML/CSS wireframes | Location page wireframes |
| **amber-pegasus** | HTML/CSS (DaisyUI wireframes) | C2C journey wireframes |
| **azure-phoenix** | Unknown (no pyproject.toml found) | |
| **neon-valkyrie** | Python, TOML | Hermes additions |
| **vermillion-quetzalcoatl** | Python (keyword research), TOML | SEO/keyword research |
| **scarlet-anubis** | Unknown (no manifest files found) | |
| **MCP Hub (playwright-mcp)** | TypeScript, JSON | Browser automation MCP |
| **Obsidian vault** | Markdown, YAML frontmatter, CSS | Note-taking, kanban, session artefacts |

## Language Coverage

| Language | % of Repo | Seen In |
|----------|-----------|---------|
| Python | ~70% | Nearly every project |
| TOML | ~15% | pyproject.toml in every Python project |
| Markdown | ~8% | AGENTS.md, TASK-BRIEFs, docs, vault |
| TypeScript/JS | ~4% | purple-odin, playwright-mcp |
| HTML/CSS | ~2% | Wireframe projects |
| YAML | ~1% | Configs, CI, Obsidian frontmatter |
| JSON | ~1% | package.json, MCP configs |

## OpenCode Built-in LSP Servers (relevant ones)

| Server Name | Extensions | Install Required | Priority |
|-------------|------------|-----------------|----------|
| `pyright` | `.py`, `.pyi` | `npm install -g pyright` | **Tier 1** — Python is dominant |
| `ruff` | `.py` | `pip install ruff` (or system) | **Tier 1** — Already in toolchain |
| `oxlint` | `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.mts`, `.cts`, `.vue`, `.astro`, `.svelte` | `npm install -g oxlint` (or bun) | **Tier 2** — Fast Rust-based lint for JS/TS |
| `typescript` | `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.mts`, `.cts` | `npm install -g typescript typescript-language-server` | **Tier 2** — purple-odin + MCP |
| `oxlint` (type-aware) | `.ts`, `.tsx`, `.js`, `.jsx` | `npm install -g oxlint @oxc-project/typescript-language-server` | **Tier 2** — Alternative TS LSP using Oxc resolver |
| `yaml-ls` | `.yaml`, `.yml` | Auto-installed | **Tier 2** — Zero-effort, high volume |
| `bash` | `.sh`, `.bash`, `.zsh` | Auto-installed | **Tier 2** — Shell scripts everywhere |
| `toml` (taplo) | `.toml` | Built-in | **Tier 3** — pyproject.toml only |
| HTML/CSS | `.html`/`.css` | Built-in (vscode servers) | **Tier 3** — Wireframe work |
| markdown (marksman) | `.md` | Auto-installed | **Tier 3** — Docs benefit less |

## Recommended `opencode.json` (Pantheon-wide)

Place at `/mnt/z/pantheon/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "lsp": {}
}
```

**Note:** OpenCode's JSON schema requires `command` arrays for individual server entries — the `"<server-name>": {}` format will fail with `Missing key lsp.<server-name>.command`. Using `"lsp": {}` (empty object) enables all 30+ built-in LSPs. Servers whose binaries are installed (pyright, ruff, oxlint, typescript-language-server, bash-language-server, yaml-language-server, taplo) will activate; those missing (rust-analyzer, gopls, etc.) are silently skipped. No explicit disable list needed.

If you need to disable specific built-in servers, use the `disabled` key:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "lsp": {
    "rust": { "disabled": true }
  }
}
```

## Install Commands

```bash
# Python LSP
npm install -g pyright

# Ruff as LSP (newer ruff versions have built-in server)
pip install ruff

# TypeScript
npm install -g typescript typescript-language-server

# Verify all
pyright --version
ruff --version
typescript-language-server --version
```

## Verification

After configuration, verify LSP is active by running OpenCode on a Python file:
```bash
cd /mnt/z/pantheon
opencode debug lsp diagnostics projects/purple-phoenix/main/agent_context/scripts/pantheon_init.py
```

This should return diagnostics (type errors, lint issues) rather than "no diagnostics" or "LSP not configured."
