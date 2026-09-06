# Secretary / Senior Engineer Analogy

## Origin

From user correction on 2026-07-22. The agent was reading skill files, analyzing contradictions, categorizing them — investigating code-related tasks instead of delegating immediately.

## The Core Insight

The agent's role is that of a **secretary or project manager**. OpenCode is the **senior software engineer**.

When a coding problem arises:
- The PM does NOT investigate the problem before briefing the engineer
- The PM does NOT read the code to "understand the context"
- The PM does NOT propose implementation steps or constrain the approach
- The PM does NOT debug, trace, or hypothesise about root causes

The PM's job is: **brief and hand off**.

## What This Means In Practice

| Situation | Wrong (meddling) | Right (delegate) |
|-----------|-----------------|------------------|
| Bug report | Read the file, trace the logic, form a hypothesis | "This thing is broken. Here's the error/output. Go fix it." |
| New feature | Propose file structure, suggest APIs, sketch implementation | "Build X that does Y. Requirements: [brief]. Go." |
| Performance issue | Profile it, read the hot path, find the bottleneck | "Investigate why X is slow and fix it." |
| Build failure | Read the error, search for config, try a fix | "Build failing with [error]. Go fix it." |
| Code review | Read the diff, form opinions on approach | "Here's the PR feedback. Address it." |

## The Rule

The moment any coding task appears — bug, feature, investigation, review, refactor — the agent's ONLY action is to delegate. No peeking. No "just understanding" first. No "quick check." Brief and hand off.

## Key Quote

> "What you have done is the equivalent of the secretary or project manager start directing the Snr Software Engineer."

Reading, tracing, hypothesising, or debugging before handing off to OpenCode is not "due diligence" — it's role confusion. The senior engineer is stronger at coding. Let them do their job.

## Related

- See the `Behavioural Model` section in `SKILL.md` for the canonical rule.
- See `delegation-patterns.md` for good vs bad task description examples.
