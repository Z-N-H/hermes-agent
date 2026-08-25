---
name: github
description: "GitHub end-to-end: auth, repos, PRs, code review, issues, releases, secrets, Actions, and codebase analytics."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [github, git, repo, pr, code-review, issues, releases, ci, actions, auth]
    related_skills: [requesting-code-review, test-driven-development, subagent-driven-development]
---

# GitHub

End-to-end GitHub workflows using the `gh` CLI and git. Covers auth, repository management, pull requests, code review, issues, releases, secrets, Actions, and codebase analytics.

## Auth Setup

### Detect current state

```bash
gh auth status
```

### Authenticate with a personal access token (PAT)

```bash
echo "YOUR_PAT" | gh auth login --with-token
# or interactive: gh auth login
```

### SSH key setup

```bash
ssh-keygen -t ed25519 -C "your_email@example.com" -f ~/.ssh/id_ed25519
gh ssh-key add ~/.ssh/id_ed25519.pub --title "$(hostname)-$(date +%Y%m%d)"
```

### Enterprise Server

```bash
gh auth login --hostname github.mycompany.com
gh auth status --hostname github.mycompany.com
```

See `scripts/gh-env.sh` for a full environment-check script.

## Repository Management

### Clone / create / fork

```bash
gh repo clone owner/repo
gh repo create my-project --public --source=. --push
gh repo fork owner/repo --clone=true
```

### Releases

```bash
gh release create v1.0.0 --title "1.0.0" --notes-file CHANGELOG.md
gh release upload v1.0.0 dist/*.whl
```

### Secrets and variables

```bash
gh secret set API_KEY --body "$API_KEY_VALUE"
gh variable set DEPLOY_ENV --body "production"
```

### Remotes and sync

```bash
gh repo sync owner/repo --branch main
```

See `references/github-api-cheatsheet.md` for the full `gh` command matrix (repos, releases, secrets, variables, workflows, runners, orgs, teams).

## Pull Request Workflow

### Branch and commit

```bash
git checkout -b feature/short-description
git add -A && git commit -m "feat: add short description"
```

### Conventional commits quick reference

- `feat:` — new feature
- `fix:` — bug fix
- `docs:` — documentation only
- `style:` — formatting, no code change
- `refactor:` — code change that neither fixes a bug nor adds a feature
- `perf:` — performance improvement
- `test:` — adding or correcting tests
- `chore:` — build process or auxiliary tool changes

See `references/conventional-commits.md` for the full spec and examples.

### Open PR

```bash
gh pr create --title "feat: add rate limiter" --body-file .github/PULL_REQUEST_TEMPLATE.md
```

Or use templates:
- `templates/pr-body-bugfix.md` — bug fix PR template
- `templates/pr-body-feature.md` — feature PR template

### CI and merge

```bash
gh pr checks 123 --watch       # wait for CI
gh pr merge 123 --squash       # squash and merge
gh pr merge 123 --auto --squash  # auto-merge when CI passes
```

### CI troubleshooting

When checks fail:
1. `gh run list --branch $(git branch --show-current)` — find the run.
2. `gh run view <run-id> --log` — read the failure log.
3. Re-run: `gh run rerun <run-id>`.

See `references/ci-troubleshooting.md` for detailed GitHub Actions debugging steps.

## Code Review

### Local review (your own changes)

Before pushing, run the pre-commit verification pipeline from `requesting-code-review`:
- `git diff --cached`
- static security scan
- baseline tests and linting
- independent reviewer subagent

### GitHub PR review (other people's PRs)

```bash
gh pr checkout 123              # check out the PR branch
gh pr diff 123                  # view the diff
gh pr review 123 --comment      # add a general comment
gh pr review 123 --request-changes --body "See line notes"
```

For inline comments on specific lines, use the REST API or web UI. The `gh` CLI does not yet support inline review comments directly — use:

```bash
curl -X POST \
  -H "Authorization: token $(gh auth token)" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/owner/repo/pulls/123/comments \
  -d '{
    "body": "Consider using a constant here.",
    "commit_id": "abc123...",
    "path": "src/auth.py",
    "side": "RIGHT",
    "line": 42
  }'
```

See `references/review-output-template.md` for a structured review report format.

## Issues

### Create

```bash
gh issue create --title "Bug: login fails on Safari" --body-file templates/bug-report.md
gh issue create --title "Feature: dark mode" --body-file templates/feature-request.md
```

### Triage

```bash
gh issue list --label bug --state open
gh issue edit 123 --add-label "priority-high" --assignee @me
gh issue close 123 --comment "Fixed in v1.2.3"
```

## Codebase Analytics

Use `pygount` for quick LOC and language breakdown:

```bash
pip install pygount
pygount --format=summary .
pygount --format=cloc-xml . > report.xml
```

This is useful for:
- Estimating migration effort
- Finding monorepo hotspots
- Generating project health dashboards

## Common Pitfalls

- **`gh` not installed or not authenticated** — always run `gh auth status` first.
- **SSH key not added to GitHub** — `git push` will prompt for password; use HTTPS with PAT or add the SSH key.
- **Enterprise hostname mismatch** — `gh` commands default to `github.com`; pass `--hostname` for GHE.
- **Token lacks scopes** — `repo` scope for private repos, `workflow` scope for Actions secrets.
- **Conventional commit mismatch** — some repos enforce conventional commits in CI; follow the repo's `CONTRIBUTING.md`.
