# Hermes Core Customisation Workflow — Strategy A (Local Branch)

Session-derived reference for safely modifying Hermes source code and preserving changes across `hermes update` operations.

## Why This Exists

`hermes update` runs `git pull --ff-only origin main` inside `~/.hermes/hermes-agent/`. Any uncommitted code edits are auto-stashed and restored, but if upstream changed the same files, the restore conflicts and your changes remain in the stash. A dedicated branch workflow eliminates this risk.

---

## One-Time Setup

```bash
cd ~/.hermes/hermes-agent
git checkout -b znh/custom
git add -A
git commit -m "znh: customisations snapshot"
git checkout main
```

Your edits are now safe on `znh/custom`. Hermes continues to run on `main`.

---

## Daily Workflow

### Normal operation (no update today)

Do nothing. Hermes runs on `main`.

### Updating

**Don't run bare `hermes update` on this checkout** (see the incident note
below). Run the wrapper — it does branch dance + rebase + dependency re-sync
into **both** `venv/` and `.venv/` + gateway restart for you:

```bash
/mnt/z/pantheon/.hermes/scripts/safe_hermes_update.sh
```

Manual equivalent (only when bypassing the wrapper):

```bash
cd ~/.hermes/hermes-agent
hermes update                                  # from main only
git checkout znh/custom
git rebase main
# If conflicts: resolve, then `git add <resolved-file> && git rebase --continue`
VIRTUAL_ENV=$PWD/venv  uv pip install -e '.[all]'   # re-sync BOTH venvs from
VIRTUAL_ENV=$PWD/.venv uv pip install -e '.[all]'   # znh/custom's pins
systemctl --user restart pantheon-hermes-gateway.service
cd ~ && hermes
```

If the rebase is clean, your customisations are now on top of the latest upstream.

---

## How `hermes update` Interacts with Branches

1. Stash uncommitted changes
2. If current branch != target branch (default `main`), switch to target
3. `git fetch origin <branch>` → `git pull --ff-only origin <branch>`
4. If ff-only fails, `git reset --hard origin/<branch>`
5. Restore stashed changes
6. Reinstall Python deps, rebuild UI

**Key consequence:** running `hermes update` while on `znh/custom` switches away to `main`, updates **with main's dependency pins**, and **does not return** to `znh/custom` — stranding the venv(s) on the wrong branch's pins (2026-08-22 incident: every MCP tool call broke in the live gateway). This is why updates here go through `safe_hermes_update.sh`, which returns to `znh/custom` no matter what and re-syncs both venvs from `znh/custom`'s `pyproject.toml`.

---

## Adding New Customisations

```bash
cd ~/.hermes/hermes-agent
git checkout znh/custom
# ... edit files ...
git add <files>
git commit -m "Describe change"
git checkout main
```

---

## Migrating to Strategy B (GitHub Fork)

If you outgrow the local branch:

```bash
cd ~/.hermes/hermes-agent
git remote rename origin upstream
git remote add origin https://github.com/YOURUSER/hermes-agent.git
git push -u origin znh/custom
```

Then keep `main` synced manually:

```bash
git checkout main
git pull upstream main
git push origin main
git checkout znh/custom
git rebase main
git push --force-with-lease origin znh/custom
```

---

## Safe vs. At-Risk Locations

| Safe (outside git repo) | At risk (inside `hermes-agent/`) |
|------------------------|-----------------------------------|
| `~/.hermes/config.yaml` | `run_agent.py` |
| `~/.hermes/.env` | `cli.py` |
| `~/.hermes/skills/` | `agent/*.py` |
| `~/.hermes/skins/` | `hermes_cli/*.py` |
| `~/.hermes/plugins/` | `gateway/*.py` |
| `~/.hermes/memories/` | `tools/*.py` |
| `~/.hermes/cron/` | `ui-tui/src/*` |

**Rule:** anything under `~/.hermes/` **except** the `hermes-agent/` directory is immune to `hermes update`.

---

## Troubleshooting

**Update failed because I was on `znh/custom`**

```bash
cd ~/.hermes/hermes-agent
git checkout main
hermes update
# Then rebase znh/custom as normal
```

**Rebase has conflicts**

```bash
git status        # see conflicting files
# edit files, resolve conflict markers
git add <file>
git rebase --continue
```

**What does `znh/custom` have that `main` doesn't?**

```bash
git log main..znh/custom --oneline
git diff main..znh/custom --stat
```

**Hermes won't start after rebase**

```bash
git checkout main        # roll back to stock
git checkout znh/custom
python -m py_compile run_agent.py cli.py agent/*.py
```

**Fork sync: `hermes update` says "Your fork has N commits not on upstream"**

This is the built-in fork detector bailing because `origin/main` has your custom commits. It skips upstream sync to protect them. Use Strategy A or manually sync `main` from `upstream` before updating.
