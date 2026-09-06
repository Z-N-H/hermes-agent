# Delegation Patterns — Concrete Examples

> Part of the `opencode-worker` skill. Shows what compliance looks like in practice.

## Golden Rule

**Read nothing. Investigate nothing. Delegate immediately.**

When a user says "fix it," "tweak it," "change this," "investigate," "debug," "review," or anything pointing at code, your ONLY action is to delegate to OpenCode. You do not:
- Read the file first to "understand the problem"
- Hunt through grep/search to "confirm the scope"
- Quick-check `git diff` to "see what's going on"
- Open the file to "verify the bug is real"

This is not withholding context — it's respecting the boundary. OpenCode reads your brief and the code together. You reading the code first is busywork that adds turns without value.

---

## Pattern 1: Bug Fix

**User says:** "The login form doesn't validate email format"

❌ **WRONG — investigating before delegating:**
```
1. read_file auth/login.py  (investigating!)
2. search_files "email"     (investigating!)
3. "I see the validate() function lacks email regex"  (diagnosing!)
4. opencode run "Add email validation..."
```

✅ **RIGHT — delegate immediately:**
```
opencode run "The login form in src/auth/login.py doesn't validate email format.
Submit an invalid email and it silently accepts it. Fix it so email validation
fires on submission with a clear error message for bad formats."
```

---

## Pattern 2: Feature Implementation

**User says:** "Add a dark mode toggle to the settings panel"

❌ **WRONG — specifying steps:**
```
opencode run "Step 1: Create src/components/DarkModeToggle.jsx.
Step 2: Add a state variable. Step 3: Toggle a CSS class on body..."
```

✅ **RIGHT — stating the problem:**
```
opencode run "Add a dark mode toggle to the settings panel in
src/components/SettingsPanel.jsx. The app uses CSS custom properties
(--bg, --text, etc.) in styles/theme.css. Toggle should persist
preference in localStorage and apply immediately. No page reload."
```

---

## Pattern 3: Config Change

**User says:** "Change the API timeout from 30s to 60s"

❌ **WRONG — quick fix via patch/write_file:**
```
patch /path/to/config.py old_string="TIMEOUT=30" new_string="TIMEOUT=60"
```

✅ **RIGHT — delegate:**
```
opencode run "Change the default API timeout from 30 seconds to 60 seconds
in src/config.py. Check that all HTTP client references still work with
the new value and update any docstrings or type hints that say '30s'."
```

---

## Pattern 4: Code Review

**User says:** "Review PR #42, check for security issues"

❌ **WRONG — reading the diff and analyzing:**
```
terminal "gh pr diff 42"  (reading code!)
"I see the SQL query is constructed with f-strings..." (analyzing!)
```

✅ **RIGHT — delegate the review:**
```
opencode run "Review the changes in the current branch (PR #42).
Check for: SQL injection, XSS, missing input validation, hardcoded
secrets, and any logic errors. Run the existing test suite and report
what passes and what fails. This is a code review pass — output findings
with file:line references and severity labels."
```

---

## Pattern 5: Investigating a Test Failure

**User says:** "The CI test 'test_user_login' failed on main"

❌ **WRONG — triaging yourself:**
```
read_file tests/test_auth.py | grep test_user_login  (reading!)
terminal "uv run pytest tests/test_auth.py::test_user_login -x"  (running!)
```

✅ **RIGHT — delegate the investigation:**
```
opencode run "The test 'test_user_login' failed in CI on main branch.
Read the test in tests/test_auth.py and identify why it's failing.
Run it locally and capture the error. Fix the underlying issue and
verify the test passes. Do not skip or delete the test."
```

---

## Pattern 6: Recovering from a Partial OpenCode Run

**User says:** "The opencode run timed out halfway through"

❌ **WRONG — finishing it yourself:**
```
read_file src/feature.py  (reading!)
patch src/feature.py old_string="..." new_string="..."  (editing!)
"I'll finish what opencode started"
```

✅ **RIGHT — fresh delegation:**
```
opencode run "Previous run of this task timed out mid-implementation.
Files in the worktree may be partially modified. Read the full state
of the worktree, TASK-BRIEF.md, and any partial changes, then complete
the implementation. Verify with the existing tests."
```

---

## Pattern 7: "Just a Quick Look" (most common trap)

**User says:** "Can you check if we use bcrypt or argon2 for passwords?"

❌ **WRONG — satisfying curiosity:**
```
search_files "bcrypt"  # This is reading code!
search_files "argon2"  # Still reading code!
```

✅ **RIGHT — delegate even "just looking":**
```
opencode run "Find out what password hashing algorithm the project uses
(auth/login.py, models/user.py, any security-config files). Report the
library name, the exact function calls, and the config values (work factor,
salt length, etc.). Don't change anything — this is a discovery pass."
```

**Why this matters:** Every file read is a test of self-discipline. If you read a file to "just understand the type signature" and find a bug, you'll be tempted to fix it. The boundary exists to prevent this exact cascade. Read nothing, delegate everything.

---

## Pattern 8: OpenCode Produced Error Output

**User says:** "opencode is back with an error"

❌ **WRONG — debugging the output yourself:**
```
cat the error log
search for the error message in the codebase
```

✅ **RIGHT — feed the error back to opencode:**
```
opencode run "Your previous run produced this error:
<paste error output>
Fix whatever caused this error. Read the relevant files, understand the
problem, and fix it. Verify afterwards."
```

---

## Summary: The Two-Question Test

Before touching any file with a code-related name, ask:

1. **"Am I reading or modifying code?"** → Delegate to OpenCode.
2. **"Could this be code?"** → Delegate to OpenCode.

If the answer isn't an unequivocal "no, this is documentation or a plan," default to delegation. Saying "I'll just check one thing first" is how every boundary violation in this project started.
