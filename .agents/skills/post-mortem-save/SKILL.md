---
name: post-mortem-save
description: >
  Write and save a post-mortem (engineering incident record) to both the
  project docs/ directory AND the Claude Vault wiki after a bug is fixed
  or an incident is resolved.
  Trigger when the user says things like "save the post-mortem", "document this
  fix to the vault", "write a post-mortem for this bug", "log this incident",
  "create a retro entry", or any equivalent phrase after a debugging session.
  Always use this skill — not a plain response — when the user wants to persist
  an incident record somewhere lasting.
---

# post-mortem-save

Save a structured post-mortem record to **two destinations**:

1. **Project `docs/`** — full technical detail, lives in the repo, written directly
2. **Claude Vault wiki** — written via wiki-ingest workflow (classifier → writer)
   for consistent Thai prose and proper wiki conventions

Both destinations are always written in the same run unless the user explicitly
asks for only one.

---

## Locations

**Project docs (written directly):**
```
<project-root>/docs/retrospectives/<service>-retro-<slug>.md
```

**Claude Vault raw staging (written before wiki-ingest):**
```
C:\Users\User\First\notes\claude-vault\raw\<service>-retro-<slug>.md
```

**Claude Vault wiki (written by wiki-writer via wiki-ingest):**
```
C:\Users\User\First\notes\claude-vault\wiki\
```

---

## Step 1 — Confirm required inputs

Refuse to write anything if any of these is missing or unknown.

- **Reliable repro** — the bug was reproducible deterministically before the fix
- **Root cause identified** — the mechanism is understood, not just a hypothesis
- **Fix identified** — there is a file, commit, branch, or code change to point to
- **Fix validated** — the repro now passes (or explicitly mark as "Pending")

---

## Step 2 — Identify project root

Look at the conversation to identify which project/codebase is involved.
Common locations: `C:\Users\User\First\project\<project-name>\`
If ambiguous, ask the user before writing anything.

---

## Step 3 — Derive the file name

```
<service>-retro-<slug>.md
```

- `<service>` = leaf directory name (e.g., `vas`, `nestjs`, `vending-api`)
- `<slug>` = 3–6 word kebab-case description of what broke
  - Good: `fastmcp-mount-no-tools`, `pip3-not-found-bootstrap`
  - Bad: `bug-fix`, `the-issue`, `2026-05-21-fix`

Same filename base is used for both project docs and raw staging.

---

## Step 4A — Write the project docs file (direct write)

**Path:** `<project-root>/docs/retrospectives/<service>-retro-<slug>.md`

Create `docs/retrospectives/` if it does not exist.

Full technical detail — exact file paths, line numbers, diff summaries, CLI commands.
Write in whatever language fits the project (English is fine).

```markdown
---
date: YYYY-MM-DD
status: resolved | pending-validation
---

# Retro: <title>

## Summary
One paragraph: what broke, what the fix was, commit/PR pointer.

## Symptom
Exact observable failure — error message, log line, terminal output.

## Root Cause
File, function, line number, or config key + causal chain root → symptom.

## Why It Produced the Symptom
*(optional)* Explicit link if not obvious.

## Fix
File path + before/after diff or commit hash. Explain why it works.

## How It Was Found
Tools used, hypotheses tested and rejected.

## Why It Slipped Through
*(optional, blameless)* Gap in CI, code review, or process.

## Validation
Evidence the fix works. If not yet: **Pending**.

## Action Items
| # | What | Owner | Status |
|---|------|-------|--------|
| 1 | ... | ... | Open |
```

---

## Step 4B — Save raw retro content to raw/ for wiki-ingest

Write the retro content as a **source document** into the vault's `raw/` folder.
This becomes the input to the wiki-ingest workflow — do NOT write to wiki/ directly.

**Path:** `C:\Users\User\First\notes\claude-vault\raw\<service>-retro-<slug>.md`

Write in English. Include all incident details clearly structured with headings
so wiki-classifier and wiki-writer can understand and classify correctly.

```markdown
# <Title> — Post-Mortem

**Project:** <project name>
**Service/Component:** <service or tool>
**Date:** YYYY-MM-DD
**Status:** resolved | pending-validation

## What Broke
<symptom>

## Root Cause
<mechanism — file, function, config key, causal chain>

## Fix
<what changed and why it works>

## Lesson Learned
<transferable insight — what to watch for in future projects>

## References
- Project docs: `<project-root>/docs/retrospectives/<filename>.md`
- Commit/PR: <link if available>
```

---

## Step 5 — Run wiki-ingest workflow on the raw file

After writing the raw file, delegate to the wiki-ingest workflow in sequence.
**Never write to wiki/ directly — always go through classifier and writer.**

### 5a — Spawn wiki-classifier

```
Classify the following raw file for wiki ingestion.
File path: C:\Users\User\First\notes\claude-vault\raw\<service>-retro-<slug>.md

Note: this is a post-mortem / retrospective record. Place under:
- wiki/projects/<project>/retrospectives/ if project-specific bug
- wiki/knowledge-base/technology/<category>/<tool>/ if general tech finding
```

Wait for classification result. If confidence < 70, ask the user before continuing.

### 5b — Show classification to user briefly

```
จะวางที่: <target_path>
เหตุผล: <reasoning>
```

### 5c — Spawn wiki-writer

```
Write a wiki page for the following raw file.

Raw file path: C:\Users\User\First\notes\claude-vault\raw\<service>-retro-<slug>.md
Classification result:
<full CLASSIFICATION block from 5a>

Follow the ingest skill rules. Write the page at the target path,
create any new directories listed, update the parent index, and log to wiki-log.md.
```

Wait for wiki-writer to finish before reporting to user.

---

## Step 6 — Project docs directory

Create if not exists:
```
<project-root>/docs/retrospectives/
```

Vault directories are handled by wiki-writer — only manage project side here.

---

## Step 7 — Report back

1. Full path of **project docs file** written
2. Full path of **raw staging file** written
3. What wiki-writer reported: vault path, index updated, word count
4. Any pending validations
5. Offer `/management-talk` for non-technical summary

---

## What this skill does NOT do

- Does not write vault wiki files directly — always delegates to wiki-ingest workflow
- Does not write while root cause is still a hypothesis
- Does not create customer-facing incident reports
- Does not overwrite existing retro files — create new and cross-link
- Does not skip project docs even for general tech findings
