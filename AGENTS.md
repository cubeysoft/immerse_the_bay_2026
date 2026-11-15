# Agent instructions

Make the smallest complete change that solves the task. Keep the codebase easy to understand for someone seeing it for the first time.

## Before changing anything

- Read `LEDGER.md` first. If it does not exist, create it using the format below.
- Inspect the relevant code, tests, and existing conventions before deciding how to implement the change.
- Check the actual code when a note seems stale. Correct `LEDGER.md` instead of carrying an unverified claim forward.
- Do not rely on chat history or memory for project state. It may disappear after context compaction.

## Code

- **KISS:** Prefer the simplest implementation that meets the requirements. Keep control flow and data flow obvious.
- **DRY:** Reuse existing code and remove meaningful duplication. Do not create an abstraction for a coincidence.
- **YAGNI:** Build only what the current task needs. Avoid speculative features, configuration, extension points, and dependencies.
- **Modularity:** Give each module, function, and component one clear responsibility. Keep interfaces small and dependencies explicit. Split code when the split makes it easier to understand, change, or test; do not create tiny files just to satisfy a rule.
- Prefer descriptive names, straightforward functions, and established project patterns over clever shortcuts.
- Refactor complicated logic into simpler steps before adding explanations around it.
- Avoid unrelated refactors. Preserve existing behavior unless the task requires changing it.

## Comments

- Write code that explains itself. Do not comment on what a statement plainly does.
- Add a comment only when the *reason* is non-obvious: a workaround, surprising constraint, external behavior, or necessary tradeoff.
- If an algorithm needs a running commentary, simplify its design, naming, or structure first.
- Remove comments that repeat the code or no longer match it.

## Documentation and language

Write for a tired developer who has no recent context. They should be able to find the relevant files, understand what changed, and continue without asking for a recap.

- Lead with the fact, decision, instruction, or problem. Skip introductions that say nothing.
- Use plain, direct language and short sentences. Prefer concrete nouns and verbs.
- Name exact files, functions, commands, behavior, and failure cases when known. Do not replace specifics with vague claims.
- Explain *why* something unusual exists; do not narrate obvious implementation steps.
- State uncertainty and unfinished work directly. Never invent test results, decisions, or completed work.
- Use headings and lists when they make information easier to scan, not as decoration. Use sentence-case headings.
- Avoid repetitive paragraph shapes, forced groups of three, rhetorical questions with immediate answers, and summary paragraphs that only repeat prior text.
- Avoid stock contrasts such as "not just X, but Y" and "it's not about X, it's about Y."
- Avoid empty transitions and self-important phrasing: "it's worth noting," "furthermore," "in conclusion," "moving forward," "in today's landscape," "delve," "tapestry," "pivotal," "seamless," "robust," "leverage," "unlock," and "elevate" when a plain alternative works.
- Avoid hype, filler, unnecessary reassurance, excessive bolding, and overused em dashes. Do not write like a product announcement or a chatbot.
- Do not add a conclusion unless it contains a decision, warning, or next action that has not already been stated.

## Continuity: `LEDGER.md`

`LEDGER.md` at the repository root is the **single source of handoff context**. It is the starting point for every fresh session and the project state that must survive context compaction. `AGENTS.md` holds stable working rules; `LEDGER.md` holds the current state of the work.

- Keep it in Markdown (`.md`) with concise bullet points in plain language.
- Update it after every meaningful completed change, before handing off, and before context compaction when possible.
- Record what was actually implemented, where it lives, important decisions or caveats, what was verified, and the next concrete steps.
- Keep the next steps executable. Mention file paths, commands, and blockers when they matter.
- Keep it current, not exhaustive. Remove stale or superseded notes; do not turn it into a chronological diary or dump raw conversation transcripts.
- Never mark planned work as done. If work is partial, say exactly what remains.
- If code and the ledger disagree, inspect the code and fix the ledger. The ledger is the handoff record, not a substitute for checking reality.

Use this structure:

```md
# Project ledger

## Current state
- What currently works and where the important pieces live.

## Implemented
- Concrete changes made, with relevant file paths.

## Decisions and blockers
- Non-obvious decisions, constraints, and unresolved problems.

## Verification
- Checks run and their results; checks not run and why.

## Next steps
- [ ] The next specific action, including the relevant file or command.
```

- Every entry must include:
  - a date or ISO timestamp (e.g., `2026-01-13` or `2026-01-13T09:42Z`)
  - a provenance tag: `[USER]`, `[CODE]`, `[TOOL]`, `[ASSUMPTION]`
- If unknown, write `UNCONFIRMED` (never guess). If something changes, supersede it explicitly (don't silently rewrite history).


## Before finishing a task

- Run the relevant checks available in the repository. Do not claim a check passed unless it ran.
- Review the diff for unnecessary complexity, accidental changes, and stale comments or documentation.
- Update `LEDGER.md` to reflect the state left on disk, including unfinished work.
- Report what changed, what was tested, any blockers, and what to do next. Keep the handoff brief.
