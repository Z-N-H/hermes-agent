# znh-skills

Zack's bespoke Hermes skills. **Not upstream** — these exist only in this
fork, and before 2026-08-25 they existed only as untracked directories under
`/mnt/z/pantheon/.hermes/skills/` (and the `opencode` profile's own
`skills/`), with no history and no way to restore them.

Tracked here:

| Root | Contents |
|---|---|
| `skills/<category>/<name>/` | 60 skills from the main home's `skills/` that are absent from its `.bundled_manifest` (i.e. not bundled installs) |
| `archive/<name>/` | the 10 skills in the Curator's `.archive/` at capture time |
| `profiles/opencode/...` | 11 skills bespoke to the `opencode` profile's own `skills/` |

The remaining skills in `$HERMES_HOME/skills/` are upstream bundled installs
tracked by `.bundled_manifest`; they re-seed from `skills/` in this repo and
are not captured here.

## Install

```bash
# Run FROM THE CANONICAL RUNTIME CHECKOUT so the registered path is durable:
cd /mnt/z/pantheon/.hermes/hermes-agent
git pull           # after this branch has merged
./znh-skills/install.sh
hermes skills list # every znh skill appears once, usual categories
```

The installer is idempotent and line-based (no YAML rewrite, comments
preserved); it:

1. Appends `./znh-skills/skills` to `skills.external_dirs` in
   `$HERMES_HOME/config.yaml` (and `profiles/opencode/` for the opencode
   profile's config). Backups land at `config.yaml.bak-znh-skills`.
2. Replaces `$HERMES_HOME/skills/.archive` with a symlink to
   `./znh-skills/archive` — identical content gets parked at
   `.archive.pre-znh-skills-bak`; diverging content is refused, not clobbered.

`HERMES_HOME` defaults to `/mnt/z/pantheon/.hermes` (the live home, same as
`znh-plugins/`).

**Important — ambiguity window:** until the local copies are retired (next
section), `skill_view` by bare name refuses with an "ambiguous skill name"
error when a name exists in both roots; categorized paths
(`skill_view(category/name)`) keep working. So install and retire in the same
sitting, and only after the checkout that owns the registered path has been
pulled.

## Why external_dirs rather than the znh-plugins symlink pattern

Hermes has a native config for extra skill roots
(`agent/skill_utils.py: get_external_skills_dirs`), unlike the plugin scanner.
With external dirs:

- discovery is local-first with name dedup across roots
  (`tools/skills_tool.py: _find_all_skills`), so a stale local copy shadows
  the tracked one instead of duplicating it;
- the roots count as trusted, so `skill_view` logs no
  "outside trusted skills directory" security warning;
- the Curator is explicitly forbidden from touching external-dir skills
  (`agent/curator.py` — "DO NOT touch bundled, hub-installed, or external-dir
  skills"), which is what you want once git is the source of truth: no
  Curator pass rewrites tracked files behind your back.

Categories still come from the path (`<category>/<name>/SKILL.md`, the same
layout the local root uses), so the banner grouping is unchanged.

## Retiring the shadowed local copies

After install + `hermes skills list` shows the skills resolving from
znh-skills, delete the home-local copies that would otherwise shadow the
tracked ones (local wins in the dedup). Same layout, so:

```bash
REPO=/mnt/z/pantheon/.hermes/hermes-agent   # the runtime checkout
cd /mnt/z/pantheon/.hermes/skills
(cd "$REPO/znh-skills/skills" && find . -name SKILL.md) | while read -r f; do
    d="$(dirname "$f")"; [ -d ".$d" ] && echo "rm -rf .$d"
done   # review the list first, then pipe to sh

cd /mnt/z/pantheon/.hermes/profiles/opencode/skills
(cd "$REPO/znh-skills/profiles/opencode" && find . -name SKILL.md) | while read -r f; do
    d="$(dirname "$f")"; [ -d ".$d" ] && echo "rm -rf .$d"
done
```

Bundled-manifest skills and `DESCRIPTION.md` files stay. Only remove the
copies after the external dir is verified live — until then they are the
fallback.

## Editing

Edit skills in this repo, commit, push. The runtime reads the tracked files
via the external dir; there is no copy step in the edit loop.

## Layout test

`tests/znh/test_znh_skills_layout.py` checks that every captured skill has a
parseable SKILL.md frontmatter block, names are unique per root, and the
installer stays syntactically valid.
