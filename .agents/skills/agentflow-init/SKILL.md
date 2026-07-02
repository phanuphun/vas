---
name: agentflow-init
description: Initialize agentflow agent orchestration structure for a new project. Creates AGENTS.md, INSTRUCTIONS.md (standalone) or monorepo root structure, and .agents/ directory with README, config template, and empty agent/skill/workflow directories. Use when starting a new project that needs AI agent orchestration.
---

# agentflow-init

Set up the agentflow agent orchestration structure for a new project from scratch.

## Step 1 — Ask project details

Ask the user these questions before doing anything:

1. **Project type** — standalone or monorepo?
2. **Project name and one-line overview** — e.g. `"ATS — Resume ingest system using Gemini AI"`
3. **Vault skills path** (optional) — path to your global vault skills directory (e.g. `/path/to/claude-vault/.agents/skills`). Skip to configure later via `agentflow-skill`.

Wait for all answers before proceeding.

## Step 2 — Confirm target directory

State the current working directory and confirm this is where files will be created. If the user wants a different path, use that path for all file operations.

## Step 3 — Generate files

### Standalone

**`AGENTS.md`**

```markdown
# <Project Name>

## Project Configuration

**Type:** standalone

---

## Overview

<overview>

---

## Agent & Skill Resolution

**All AI tools (Claude Code, Cursor, Codex, and others) — read this section first.**

Full protocol is in `.agents/README.md` → section **"Agent Loading Protocol (All Tools)"**.

### Loading Order (required for every tool)

1. Read `@.agents/README.md` — this is the single source of truth for agent rules and loading protocol
2. Read `@.agents/config.json` → get `agentsPath`, `wikiPath`, and `skillsPath`
3. List and read all `.md` files under `agentsPath` — interpret each as an agent definition using your tool's own conventions
4. Read the relevant workflow file from `.agents/workflows/` before running any pipeline:
   - Feature development → `@.agents/workflows/code-factory.md`
   - Wiki ingestion → `@.agents/workflows/wiki-ingest.md`
   - Project documentation → `@.agents/workflows/project-doc.md`
5. Follow workflow steps in order — for each step, re-read the agent's `.md` file and apply in-context
6. When a skill is needed, resolve in this order:
   - Project-level: `@.agents/skills/<name>/SKILL.md`
   - Global: `skillsPath` from config → `<name>/SKILL.md`

❌ Do not hardcode agent or skill paths. Always resolve from `@.agents/config.json` at runtime.

---

## Before Any Code Task

Read `INSTRUCTIONS.md` before writing, editing, or planning any code.
This file contains project conventions, directory structure, env vars, and testing rules.

---

## Write Safety

Before writing any document, ingesting files, or creating new files in the workspace:

1. Check if a vault directory exists via `.agents/config.json` → `wikiPath`
2. If no vault directory is found → STOP. Ask the user where to save and whether to create it.
3. Applies to: wiki ingestion, documentation generation, new file creation, and any write outside source code edits.

❌ Never silently create documentation or ingest files when no vault/target directory exists.

---

## Wiki

Project wiki: see `.agents/config.json` → `wikiPath`

---

## CHANGELOG

ก่อน commit ทุกครั้ง ให้อัปเดต `CHANGELOG.md` เป็น **ภาษาไทย**:
- หากวันที่ยังไม่มี → สร้าง `## [YYYY-MM-DD]` ใหม่ที่ด้านบนสุด
- หากวันที่ซ้ำกับ entry ล่าสุด → ต่อท้าย entry เดิม ห้ามสร้างหัวข้อวันที่ซ้ำ
- Format:

  ```
  ## [YYYY-MM-DD]

  ### <หัวข้อสั้นๆ>
  - รายละเอียดสิ่งที่เปลี่ยนและเหตุผล

  ### <หัวข้อถัดไป (ถ้ามี)>
  - รายละเอียด
  ```
```

---

**`INSTRUCTIONS.md`**

```markdown
# <Project Name> — Instructions

> This file is for AI agents. For human documentation see README.md.

---

## Directory Structure

<!-- TODO: describe your project's folder structure -->

---

## Environment Variables

<!-- TODO: list required env vars and where to find their values -->

---

## Setup

<!-- TODO: step-by-step setup commands -->

---

## Testing

<!-- TODO: test framework, how to run tests, coverage requirements -->

---

## Code Style & Conventions

<!-- TODO: formatting rules, naming conventions, patterns to follow -->
```

---

**`CLAUDE.md`**

```markdown
@AGENTS.md
@INSTRUCTIONS.md
@.agents/config.json
```

---

**`.agents/README.md`** — use the template in the section below

**`.agents/config.example.json`**
```json
{
  "wikiPath": "/path/to/your/claude-vault",
  "agentsPath": "/path/to/.claude/agents",
  "skillsPath": "/path/to/your/global/skills"
}
```

Create empty directories: `.agents/agents/`, `.agents/skills/`

Create the 3 workflow files using the **Workflow File Templates** section at the bottom of this skill:
- `.agents/workflows/code-factory.md`
- `.agents/workflows/project-doc.md`
- `.agents/workflows/wiki-ingest.md`

---

### Monorepo

**`AGENTS.md`**

```markdown
# <Project Name>

## Project Configuration

**Type:** monorepo
**Services:** <!-- add via agentflow-add -->

---

## Overview

<overview>

---

## Agent & Skill Resolution

**All AI tools (Claude Code, Cursor, Codex, and others) — read this section first.**

Full protocol is in `.agents/README.md` → section **"Agent Loading Protocol (All Tools)"**.

### Loading Order (required for every tool)

1. Read `@.agents/README.md` — this is the single source of truth for agent rules and loading protocol
2. Read `@.agents/config.json` → get `agentsPath`, `wikiPath`, and `skillsPath`
3. List and read all `.md` files under `agentsPath` — interpret each as an agent definition using your tool's own conventions
4. Read the relevant workflow file from `.agents/workflows/` before running any pipeline:
   - Feature development → `@.agents/workflows/code-factory.md`
   - Wiki ingestion → `@.agents/workflows/wiki-ingest.md`
   - Project documentation → `@.agents/workflows/project-doc.md`
5. Follow workflow steps in order — for each step, re-read the agent's `.md` file and apply in-context
6. When a skill is needed, resolve in this order:
   - Project-level: `@.agents/skills/<name>/SKILL.md`
   - Global: `skillsPath` from config → `<name>/SKILL.md`

❌ Do not hardcode agent or skill paths. Always resolve from `@.agents/config.json` at runtime.

---

## Before Any Code Task

Identify which service the task belongs to, then read that service's `AGENTS.md` before writing any code.

**Services:**
<!-- updated automatically by agentflow-add -->

---

## Write Safety

Before writing any document, ingesting files, or creating new files in the workspace:

1. Check if a vault directory exists via `.agents/config.json` → `wikiPath`
2. If no vault directory is found → STOP. Ask the user where to save and whether to create it.
3. Applies to: wiki ingestion, documentation generation, new file creation, and any write outside source code edits.

❌ Never silently create documentation or ingest files when no vault/target directory exists.

---

## Wiki

Project wiki: see `.agents/config.json` → `wikiPath`

---

## CHANGELOG

ก่อน commit ทุกครั้ง ให้อัปเดต `CHANGELOG.md` เป็น **ภาษาไทย** ที่ 2 ระดับ:

1. `services/<name>/CHANGELOG.md` — เฉพาะ service นั้น
   - หากวันที่ยังไม่มี → สร้าง `## [YYYY-MM-DD]` ใหม่ที่ด้านบนสุด
   - หากวันที่ซ้ำ → ต่อท้าย entry เดิม ห้ามสร้างหัวข้อวันที่ซ้ำ
   - Format:

     ```
     ## [YYYY-MM-DD]

     ### <หัวข้อ>
     - รายละเอียดเฉพาะ service นี้
     ```

2. Root `CHANGELOG.md` — สรุปรวมทุก service ใน commit นั้น
   - หากวันที่ซ้ำ → ต่อท้าย entry เดิม ห้ามสร้างหัวข้อวันที่ซ้ำ
   - Format:

     ```
     ## [YYYY-MM-DD]

     ### <หัวข้อรวม>
     - **<service>:** สิ่งที่เปลี่ยน
     - **<service>:** สิ่งที่เปลี่ยน
     ```

   ห้ามสร้าง entry แยกต่อ service — เขียนสรุปรวมใน entry เดียว
```

---

**`CLAUDE.md`**

```markdown
@AGENTS.md
@.agents/config.json
```

> Note: monorepo ไม่มี root `INSTRUCTIONS.md` — service rules อยู่ใน `services/<name>/AGENTS.md` แต่ละตัว

---

**`.agents/README.md`** — use the template in the section below

**`.agents/config.example.json`**
```json
{
  "wikiPath": "/path/to/your/claude-vault",
  "agentsPath": "/path/to/.claude/agents",
  "skillsPath": "/path/to/your/global/skills"
}
```

Create empty directories: `.agents/agents/`, `.agents/skills/`

Create the 3 workflow files using the **Workflow File Templates** section at the bottom of this skill:
- `.agents/workflows/code-factory.md`
- `.agents/workflows/project-doc.md`
- `.agents/workflows/wiki-ingest.md`

Also create: `CHANGELOG.md` (empty file with `# Changelog` header)

Note: No service directories are created here. Use `agentflow-add` for each service.

---

## `.agents/README.md` Template

```markdown
# Agent & Skill Resolution

## Directory Structure

.agents/                 # Source of truth for all agent config
├── agents/              # Agent definitions (.md files)
├── skills/              # Skills
├── workflows/           # Pipeline documentation
├── config.json          # Machine-specific settings (gitignored — copy from config.example.json)
├── config.example.json  # Config template
└── README.md            # This file

.claude → .agents        # Symlink — lets Claude Code discover agents natively (create with agentflow-init Step 4)

## Single Source of Truth

Skills and workflows live in `.agents/`. `.claude/` is a symlink to `.agents/` for tools that use `.claude/` natively (e.g. Claude Code). Agent definitions are loaded from `agentsPath` in `.agents/config.json`. Do not hardcode agent paths.

---

## Agent Loading Protocol (All Tools)

> This protocol applies to **every AI tool** — Claude Code, Cursor, Codex, or any other agent runner. Each tool reads the same source files and interprets them according to its own native conventions. **Do not create new files** — load definitions in-context only.

### Step 1 — Read config

Read `@.agents/config.json` and extract:
- `agentsPath` — directory containing agent definition `.md` files
- `wikiPath` — path to the project wiki vault
- `skillsPath` — path to global skills directory (optional)

### Step 2 — List agent definitions

List all `.md` files under the `agentsPath` directory. Each file is one agent definition.

### Step 3 — Read and interpret each agent file

Read every `<name>.md` file from `agentsPath`. Each file defines:
- **Role** — what this agent is responsible for
- **Tools** — which tools it may use
- **Model** — suggested model tier (haiku = fast/cheap, sonnet = capable)
- **Read-only** — whether it may write files or only read
- **Input / Output** — what it receives and what it produces

**Interpret these definitions using your own tool's native conventions:**

| If you are... | How to apply the definition |
|---------------|-----------------------------|
| **Cursor** | Apply as a scoped rule set for the duration of the task — treat Role as the instruction context, Tools as allowed actions, Read-only as write permission |
| **Codex CLI** | Use Role + Tools as the system prompt framing when invoking the agent step |
| **Claude Code** | Spawn via `Agent` tool, pass the full `.md` content as the agent's prompt context |
| **Other tools** | Load Role as instruction, respect Read-only constraint, constrain tool access to match Tools list |

❌ Do not create `.cursor/rules/*.mdc`, agent config files, or any new files as part of this process — interpretation happens in-context only.

### Step 4 — Load the workflow

Before running any pipeline, read the relevant workflow file from `.agents/workflows/`:

| Task type | Workflow file |
|-----------|---------------|
| Feature development | `@.agents/workflows/code-factory.md` |
| Wiki ingestion | `@.agents/workflows/wiki-ingest.md` |
| Project documentation | `@.agents/workflows/project-doc.md` |

Follow the workflow steps in order. For each step:
1. Identify which agent to run
2. Re-read that agent's `.md` file from `agentsPath`
3. Apply the definition in-context using your tool's conventions
4. Pass the required input (defined in the workflow) to that agent step
5. Collect the output block before moving to the next step

### Step 5 — Spawn / invoke agents

Use your tool's native mechanism to invoke each agent step. Pass:
- The full agent definition content as context
- The input data specified by the workflow
- The read-only constraint if applicable

---

## Rules for AI Agents

1. Always read config first — load `agentsPath`, `wikiPath`, and `skillsPath` from `@.agents/config.json`
2. Agent definitions: read `agentsPath` from `@.agents/config.json` → `<name>.md`
3. Skills — resolve in this order:
   - Project-level: `@.agents/skills/<name>/SKILL.md`
   - Global: `skillsPath` from `@.agents/config.json` → `<name>/SKILL.md`
4. Workflows: `@.agents/workflows/<name>.md`

## Subagent Spawning

Before spawning any multi-agent workflow:

1. Read the relevant workflow file from `.agents/workflows/`
2. Follow workflow steps in order
3. Read agent definitions from `agentsPath` (in `.agents/config.json`) → `<name>.md` before spawning each agent
4. Pass the full agent definition as context to the subagent

For single agent spawning:

- Read the agent definition from `agentsPath` (in `.agents/config.json`) → `<name>.md`
- Pass the full definition as context
- Load skills: check `@.agents/skills/<name>/SKILL.md` first (project-level), then `skillsPath` from `@.agents/config.json` → `<name>/SKILL.md` (global)

## Agents

Agent definitions path: read from `@.agents/config.json` → `agentsPath`. Do not hardcode paths.

## Wiki

Wiki path: read from `@.agents/config.json` → `wikiPath`. Do not hardcode paths.
```

## Step 4 — Import vault skills

### 4.1 — Create default `agentflow-skill`

Always create `.agents/skills/agentflow-skill/SKILL.md` using the **agentflow-skill Template** at the bottom of this file. This gives every new project the ability to import more vault skills on-demand during development.

### 4.2 — Import additional skills (if skillsPath provided)

If the user provided a `skillsPath` in Step 1:

1. List all directories inside `<skillsPath>` that contain a `SKILL.md` — these are importable skills
2. Show the list and ask:

   > **"Which vault skills do you want to import into this project? Enter names separated by commas, 'all' to import everything, or 'none' to skip."**

3. Wait for the user's answer
4. For each selected skill, create a symlink in `.agents/skills/`:

   **macOS / Linux:**
   ```bash
   ln -s <skillsPath>/<name> .agents/skills/<name>
   ```

   **Windows (PowerShell):**
   ```powershell
   New-Item -ItemType SymbolicLink -Path .agents/skills/<name> -Target <skillsPath>/<name>
   ```

   > ℹ️ **Windows:** Developer Mode ต้องเปิดก่อน (Settings → System → For developers)

If `skillsPath` was not provided → skip. Tell the user: "Add `skillsPath` to `.agents/config.json` and run `agentflow-skill` to import vault skills later."

## Step 5 — Create `.claude` symlink

Create a `.claude` directory symlink pointing to `.agents/` using the Bash tool. This lets Claude Code discover agents and skills on-demand without loading everything into context upfront.

### 5.1 — Detect OS

Run via Bash:
```bash
uname -s 2>/dev/null || echo "Windows"
```

### 5.2 — Handle existing `.claude/`

Check if `.claude` already exists:

**If `.claude` is already a symlink** → skip, report "symlink already exists".

**If `.claude` is a directory** → check for files inside:
- Move any files found (e.g. `settings.local.json`) into `.agents/` first:
  ```bash
  # macOS/Linux
  mv .claude/* .agents/ 2>/dev/null; mv .claude/.* .agents/ 2>/dev/null; true
  ```
  ```powershell
  # Windows PowerShell
  Get-ChildItem -Path .claude -Force | Move-Item -Destination .agents
  ```
- Then remove the empty directory:
  ```bash
  rmdir .claude        # macOS/Linux
  ```
  ```powershell
  Remove-Item .claude  # Windows
  ```

**If `.claude` does not exist** → proceed directly to 5.3.

### 5.3 — Create symlink

**macOS / Linux:**
```bash
ln -s .agents .claude
```

**Windows (PowerShell):**
```powershell
New-Item -ItemType SymbolicLink -Path .claude -Target .agents
```

> ℹ️ **Windows note:** Developer Mode ต้องเปิดไว้ก่อน (Settings → System → For developers) ไม่เช่นนั้น command จะ error เพราะไม่มีสิทธิ์ สั่ง user ให้เปิดก่อนถ้า command fail

Confirm symlink created: `.claude → .agents`

## Step 6 — Report

List every file and directory created. Then tell the user:

- **Standalone:** "Fill in `INSTRUCTIONS.md` with your project's directory structure, env vars, setup commands, testing rules, and code conventions. Update `CHANGELOG.md` before every commit."
- **Monorepo:** "Run `agentflow-add` to add each service when ready. Each service will get its own `CHANGELOG.md`. Update both the service and root `CHANGELOG.md` before every commit."

---

## agentflow-skill Template

Write `.agents/skills/agentflow-skill/SKILL.md` verbatim with this content:

````markdown
---
name: agentflow-skill
description: Import skills from the vault (skillsPath) into the current project's .agents/skills/ via symlinks. Use during development to add or refresh vault skill imports. Run agentflow-skill whenever you want to add new skills from the vault to this project.
---

# agentflow-skill

Import vault skills into this project by creating symlinks in `.agents/skills/`.

## Step 1 — Read config

Read `@.agents/config.json` → extract `skillsPath`.

- If `.agents/config.json` not found → stop. Tell the user to run `agentflow-init` or `agentflow-migrate` first.
- If `skillsPath` not set → stop. Tell the user to add `skillsPath` to `.agents/config.json` pointing to their vault skills directory (e.g. `/path/to/claude-vault/.agents/skills`).

## Step 2 — List skills

List all directories inside `<skillsPath>` that contain a `SKILL.md` file — these are importable skills.

Also list what currently exists in `.agents/skills/` to show import status.

## Step 3 — Present selection

Show the user two lists:

```
Available vault skills at skillsPath:
  [✓] agentflow-init     (already in .agents/skills/)
  [ ] agentflow-migrate
  [ ] agentflow-add
  [ ] commit-change
  ...

Current project skills (.agents/skills/):
  agentflow-skill  ← this skill (always present)
  agentflow-init   ← symlinked from vault
```

Ask: **"Which skills do you want to import? Enter names separated by commas, 'all' to import everything, or 'none' to cancel."**

Wait for the user's answer.

## Step 4 — Create symlinks

For each selected skill that is not already present in `.agents/skills/`:

**macOS / Linux:**
```bash
ln -s <skillsPath>/<name> .agents/skills/<name>
```

**Windows (PowerShell):**
```powershell
New-Item -ItemType SymbolicLink -Path .agents/skills/<name> -Target <skillsPath>/<name>
```

> ℹ️ **Windows:** Developer Mode ต้องเปิดก่อน (Settings → System → For developers) เพื่อสร้าง symlink ได้โดยไม่ต้องรันเป็น Administrator

## Step 5 — Report

List every symlink created. Tell the user:

- Skills are now available at `.agents/skills/<name>/SKILL.md`
- Claude Code discovers them automatically via the `.claude → .agents` symlink
- To add more skills later, run `agentflow-skill` again
- To remove a skill, delete its directory/symlink from `.agents/skills/`
````

---

## Workflow File Templates

Write these files verbatim. Do not add or remove sections.

---

### Template: `.agents/workflows/code-factory.md`

```markdown
# Code Factory Pipeline

Pipeline สำหรับพัฒนา feature ใหม่ตั้งแต่ต้นจนจบ

## Flow

```
┌─────────────────────┐
│ codebase-researcher │  Step 1: Research (read-only)
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│    story-writer     │  Step 2: Write user story (Thai)
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│    spec-writer      │  Step 3: Write technical spec
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ frontend-builder    │  Step 4a: Build frontend (if needed)
│ backend-builder     │  Step 4b: Build backend (if needed)
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│   test-verifier     │  Step 5: Verify tests pass
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│    pr-reviewer      │  Step 6: Final code review
└─────────────────────┘
```

## Steps

### Step 1: codebase-researcher (Read-only)
- **Purpose:** Map codebase สำหรับ feature ที่จะทำ
- **Input:** Feature description
- **Output:** `RESEARCH FINDINGS` block (relevant files, patterns, risks)
- **Tools:** Read, Glob, Grep (read-only)
- **Model:** haiku (fast, cheap)

### Step 2: story-writer (Read-only)
- **Purpose:** เขียน user story ภาษาไทยจาก feature request + research
- **Input:** Feature request + `RESEARCH FINDINGS`
- **Output:** User story with acceptance criteria (Thai)
- **Must:** User ต้อง approve story ก่อนไป step ต่อไป
- **Tools:** Read (read-only)
- **Model:** sonnet

### Step 3: spec-writer (Write)
- **Purpose:** เขียน technical brief ที่ builder agents นำไปใช้ได้เลย
- **Input:** Approved story + `RESEARCH FINDINGS`
- **Output:** Technical spec (saved to `wiki/projects/{project}/{service}/plans/`)
- **Must:** User ต้อง approve spec ก่อน save
- **Contains:** Implementation routing (frontend/backend/build order)
- **Tools:** Read, Glob, Grep, Write
- **Model:** sonnet

### Step 4a: frontend-builder (Write)
- **Purpose:** Implement frontend ตาม spec
- **Input:** Approved spec + `RESEARCH FINDINGS`
- **Output:** `FRONTEND BUILD RESULT`
- **Owns:** Pages, components, hooks, styling, frontend tests
- **Tools:** Read, Glob, Grep, Edit, Write, Bash
- **Model:** sonnet

### Step 4b: backend-builder (Write)
- **Purpose:** Implement backend ตาม spec
- **Input:** Approved spec + `RESEARCH FINDINGS`
- **Output:** `BACKEND BUILD RESULT`
- **Owns:** APIs, services, migrations, workers, backend tests
- **Tools:** Read, Glob, Grep, Edit, Write, Bash
- **Model:** sonnet

### Step 5: test-verifier (Read-only)
- **Purpose:** Verify ว่า implementation ตรงตาม spec
- **Input:** Story + spec + build results
- **Output:** `TEST VERIFICATION RESULT`
- **Tools:** Read, Glob, Grep, Bash (read-only, no edits)
- **Model:** sonnet

### Step 6: pr-reviewer (Read-only)
- **Purpose:** Final review ก่อน merge
- **Input:** Story + spec + build results + test results
- **Output:** `PR REVIEW RESULT`
- **Checks:** Scope, correctness, tests, security, architecture
- **Tools:** Read, Glob, Grep, Bash (read-only, no edits)
- **Model:** sonnet

## Notes

- สำหรับ bug fix เล็กๆ อาจไม่ต้องใช้ทุก step — ใช้แค่ subset ที่จำเป็น
- User เป็น orchestrator เอง (ไม่มี orchestrator agent)
- frontend-builder และ backend-builder ทำงาน parallel ได้ถ้าไม่มี dependency
```

---

### Template: `.agents/workflows/project-doc.md`

```markdown
# Project Documentation Pipeline

Pipeline สำหรับ document ทั้ง project เป็น wiki pages

## Flow

```
┌─────────────────┐
│  project-doc    │  Orchestrator
└────────┬────────┘
         ▼
┌─────────────────┐
│project-explorer │  Step 1: Map codebase
└────────┬────────┘
         ▼
┌─────────────────┐
│project-planner  │  Step 2: Plan doc structure
└────────┬────────┘
         ▼
┌─────────────────┐
│  wiki-writer    │  Step 3: Write each page
└─────────────────┘
```

## Steps

### project-doc (Orchestrator)
- **Purpose:** จัดการสร้าง wiki pages ทั้ง project
- **Triggers:** "document this project", "สร้าง doc โปรเจ็ค"
- **Steps:**
  1. Confirm project path
  2. Spawn project-explorer → get PROJECT ANALYSIS
  3. Handle open questions
  4. Spawn project-planner → get DOC PLAN
  5. Show plan, confirm with user
  6. Loop: spawn wiki-writer for each doc
  7. Final report

### project-explorer (Read-only)
- **Purpose:** Map codebase สำหรับ documentation
- **Input:** Project path
- **Output:** `PROJECT ANALYSIS` block (type, tech stack, services, schemas, patterns)
- **Model:** haiku (fast, cheap)

### project-planner (Read-only)
- **Purpose:** Plan documentation structure
- **Input:** `PROJECT ANALYSIS` block
- **Output:** `DOC PLAN` (list of wiki pages to create)
- **Model:** sonnet

### wiki-writer (Write)
- **Purpose:** Write wiki page for each planned doc
- **Input:** Doc plan item + source files
- **Output:** Wiki page + updated indexes + log entry
- **Model:** sonnet

## When to Trigger

- User asks to document a project codebase
- New project needs wiki documentation
- Existing docs are outdated and need refresh

## Wiki Path

Read from `.agents/config.json` → `wikiPath` field. Do not hardcode paths.
```

---

### Template: `.agents/workflows/wiki-ingest.md`

```markdown
# Wiki Ingestion Pipeline

Pipeline สำหรับ ingest raw files เข้า wiki

## Flow

```
┌─────────────────┐
│  wiki-ingest    │  Orchestrator
└────────┬────────┘
         ▼
┌─────────────────┐
│ wiki-classifier │  Step 1: Classify file
└────────┬────────┘
         ▼
┌─────────────────┐
│  wiki-writer    │  Step 2: Write wiki page
└─────────────────┘
```

## Steps

### wiki-ingest (Orchestrator)
- **Purpose:** จัดการ ingest raw file → wiki page
- **Triggers:** "ingest", "add to wiki", "บันทึกลง wiki"
- **Steps:**
  1. Confirm file exists
  2. Spawn wiki-classifier → get classification
  3. Handle low confidence (ask user)
  4. Show classification, confirm path
  5. Spawn wiki-writer → write page
  6. Report result

### wiki-classifier (Read-only)
- **Purpose:** Classify raw file → target path in wiki
- **Input:** Raw file path
- **Output:** `CLASSIFICATION` block (subject, content_type, target_path, confidence)
- **Model:** haiku (fast, cheap)

### wiki-writer (Write)
- **Purpose:** Write wiki page from classified raw file
- **Input:** Raw file + classification result
- **Output:** Wiki page + updated indexes + log entry
- **Model:** sonnet

## When to Trigger

- New research notes, specs, PDFs, transcripts, reports, or planning documents are added
- Existing source documents are substantially revised
- Implementation work depends on external research or non-code project documents
- User explicitly asks to ingest, add to wiki, document this, or update wiki

## Wiki Path

Read from `.agents/config.json` → `wikiPath` field. Do not hardcode paths.
```
