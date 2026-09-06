---
name: software-quality
description: "Development quality practices — TDD, systematic debugging, code review, spikes, and dogfooding."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [tdd, debugging, code-review, qa, testing, spikes]
---

# Software Quality Practices

## Overview

This umbrella covers the full quality lifecycle: validating ideas before building,
writing tests before code, debugging systematically instead of guessing, reviewing
code before commit, and QA-ing finished features by dogfooding them.

Each subsection is a class-level workflow. Use the subsection that matches the phase
you are in.

## 1. Spikes — Validate Before Building

Throwaway experiments to test an idea, library, or integration before committing to
a full implementation.

**Rule:** If the spike takes >2 hours, stop and ask the user. Spikes are time-boxed.

**Process:**
1. State the hypothesis clearly
2. Write the minimal code to test it
3. Run it and record results
4. Discard the code
5. Report findings to the user

A spike is NOT a prototype. It does not get committed. It answers a yes/no question.

## 2. Test-Driven Development (TDD)

**Iron law:** NO production code without a failing test first.

**Red-Green-Refactor cycle:**
1. **RED** — Write one minimal test. Run it. Confirm it fails for the right reason.
2. **GREEN** — Write the simplest code to pass. Hardcoding is allowed.
3. **REFACTOR** — Clean up duplication and names while keeping tests green.

**Never skip watching the test fail.** A test that passes immediately proves nothing.
**Never write code before the test.** If you do, delete it and start over.

**Rationalizations to reject:** "Too simple to test", "I'll test after", "Already
manually tested", "Deleting hours of work is wasteful".

## 3. Systematic Debugging

**Iron law:** NO fixes without root cause investigation first.

**Four phases (mandatory, in order):**
1. **Root Cause Investigation** — Read errors fully, reproduce consistently, check
   recent changes, gather cross-component evidence, trace data flow upstream.
2. **Pattern Analysis** — Find working examples, compare against references,
   identify differences.
3. **Hypothesis & Test** — Form one specific hypothesis. Make the smallest possible
   change to test it. If wrong, form a new hypothesis.
4. **Implementation** — Create a failing regression test. Fix the root cause (not the
   symptom). Verify. If 3+ fixes fail, question the architecture.

**Red flags that mean STOP and return to Phase 1:**
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "One more fix attempt" (after 2+ failures)
- Each fix reveals a new problem in a different place

## 4. Pre-Commit Code Review

Automated verification pipeline before code lands. Two modes:

### Mode A: Security & Quality Gate (default)
1. Capture the diff (`git diff --cached`)
2. Static security scan (hardcoded secrets, shell injection, eval/exec, SQL injection)
3. Baseline tests and linting (compare NEW failures vs baseline, not absolute pass/fail)
4. Self-review checklist
5. Independent reviewer subagent via `delegate_task`
6. Auto-fix loop (max 2 cycles)
7. Commit with `[verified]` prefix if passed

### Mode B: Parallel Cleanup Review
When user asks to "simplify" or "review recent changes", dispatch 3 parallel reviewers:
- Code Reuse (duplicated functionality)
- Code Quality (redundant state, parameter sprawl, leaky abstractions)
- Efficiency (unnecessary work, N+1 patterns, missed concurrency)

Aggregate, dedupe, apply surviving fixes directly.

## 5. Dogfooding — Exploratory QA

After implementation is complete, act as a user and try to break the feature.

**Process:**
1. Use the feature as an end user would
2. Try edge cases and invalid inputs
3. Look for visual bugs, layout issues, error-message clarity
4. Document findings with screenshots or reproduction steps
5. File issues or fix directly

**Goal:** Find bugs before users do. The agent is the first user.
