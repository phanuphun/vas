---
name: agentflow-migrate
description: Migrate an existing project's AGENTS.md to the agentflow pattern. Reads existing instruction files, classifies content into orchestration rules vs project rules, presents a migration plan, waits for approval, then generates the new structure. Never overwrites files without explicit user approval.
---

# agentflow-migrate

Migrate an existing project to the agentflow agent orchestration pattern.

## Step 1 — Read existing files

Read all instruction files that exist at the project root:
- `@AGENTS.md`
- `@CLAUDE.md`
- `@.agents/README.md`
- Any other instruction or convention files at the root (e.g. `@CONTRIBUTING.md`, `@CONVENTIONS.md`)

## Step 2 — Detect project type

Determine standalone or monorepo by checking:
- Does `services/`, `packages/`, or `apps/` directory exist with subdirectories that contain their own source code?
- Does the existing `AGENTS.md` mention multiple services?

If unclear → ask the user before continuing.

## Step 3 — Classify existing content

Go through all content from Step 1 and classify each section into one of three buckets:

| Bucket | Destination | Examples |
|--------|-------------|---------|
| **Orchestration** | Root `AGENTS.md` | Agent spawning rules, workflow routing, write safety, wiki path rules |
| **Project rules** | `INSTRUCTIONS.md` (standalone) or `services/<name>/AGENTS.md` (monorepo) | Stack, env vars, conventions, testing, setup commands, directory structure |
| **Unclear** | Ask user | Anything that doesn't clearly fit either bucket |

## Step 4 — Show migration plan

Present the full plan to the user before touching any file. Show exactly this structure:

```
MIGRATION PLAN
==============

Files that will be CREATED:
- AGENTS.md (new version — orchestration only)
- INSTRUCTIONS.md — project rules  [standalone only]
- CHANGELOG.md  [if not already exists]
- .agents/README.md  [if not already exists]
- .agents/config.example.json  [if not already exists]
- services/<name>/AGENTS.md  [monorepo only, per service]
- services/<name>/CHANGELOG.md  [monorepo only, per service, if not already exists]

Files that will be BACKED UP:
- AGENTS.md → AGENTS.md.bak

Content mapping:
- "<section name>" → AGENTS.md (orchestration)
- "<section name>" → INSTRUCTIONS.md (project rules)
- "<section name>" → needs clarification (see open questions)

Open questions:
1. [list any unclear content here]
```

Wait for the user to:
1. Approve the migration plan
2. Answer all open questions

Do not proceed until both conditions are met.

## Step 5 — Execute migration

Only after explicit user approval:

### 5.1 Backup
Rename `AGENTS.md` → `AGENTS.md.bak`

### 5.2 Create root `AGENTS.md`

Write the new `AGENTS.md` with ALL of the following sections in this exact order. Do not skip any section — every section is required regardless of whether the original file had it.

**Section 1 — Project Configuration** (always write, use detected type from Step 2)
```
## Project Configuration

**Type:** standalone
```
or for monorepo:
```
## Project Configuration

**Type:** monorepo
**Services:** <!-- add via agentflow-add -->
```

**Section 2 — Overview** (always write, use project name from existing file or ask)
```
## Overview

<one-line project description>
```

**Section 3 — Agent & Skill Resolution** (migrate from original if exists, otherwise use template)
```
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
```

**Section 4 — Before Any Code Task** (always write, content depends on type)

For standalone:
```
## Before Any Code Task

Read `INSTRUCTIONS.md` before writing, editing, or planning any code.
This file contains project conventions, directory structure, env vars, and testing rules.
```

For monorepo:
```
## Before Any Code Task

Identify which service the task belongs to, then read that service's `AGENTS.md` before writing any code.

**Services:**
<!-- updated automatically by agentflow-add -->
```

**Section 5 — Write Safety** (migrate from original if exists, otherwise use template)
```
## Write Safety

Before writing any document, ingesting files, or creating new files in the workspace:

1. Check if a vault directory exists via `.agents/config.json` → `wikiPath`
2. If no vault directory is found → STOP. Ask the user where to save and whether to create it.
3. Applies to: wiki ingestion, documentation generation, new file creation, and any write outside source code edits.

❌ Never silently create documentation or ingest files when no vault/target directory exists.
```

**Section 6 — Wiki** (migrate from original if exists, otherwise use template)
```
## Wiki

Project wiki: see `.agents/config.json` → `wikiPath`
```

**Section 7 — CHANGELOG** (always write, content depends on type)

For standalone:
```
## CHANGELOG

ก่อน commit ทุกครั้ง ให้อัปเดต `CHANGELOG.md` เป็น **ภาษาไทย**:
- หากวันที่ยังไม่มี → สร้าง `## [YYYY-MM-DD]` ใหม่ที่ด้านบนสุด
- หากวันที่ซ้ำกับ entry ล่าสุด → ต่อท้าย entry เดิม ห้ามสร้างหัวข้อวันที่ซ้ำ
- Format:

  ## [YYYY-MM-DD]

  ### <หัวข้อสั้นๆ>
  - รายละเอียดสิ่งที่เปลี่ยนและเหตุผล

  ### <หัวข้อถัดไป (ถ้ามี)>
  - รายละเอียด
```

For monorepo:
```
## CHANGELOG

ก่อน commit ทุกครั้ง ให้อัปเดต `CHANGELOG.md` เป็น **ภาษาไทย** ที่ 2 ระดับ:

1. `services/<name>/CHANGELOG.md` — เฉพาะ service นั้น
   - หากวันที่ยังไม่มี → สร้าง `## [YYYY-MM-DD]` ใหม่ที่ด้านบนสุด
   - หากวันที่ซ้ำ → ต่อท้าย entry เดิม ห้ามสร้างหัวข้อวันที่ซ้ำ
   - Format:

     ## [YYYY-MM-DD]

     ### <หัวข้อ>
     - รายละเอียดเฉพาะ service นี้

2. Root `CHANGELOG.md` — สรุปรวมทุก service ใน commit นั้น
   - หากวันที่ซ้ำ → ต่อท้าย entry เดิม ห้ามสร้างหัวข้อวันที่ซ้ำ
   - Format:

     ## [YYYY-MM-DD]

     ### <หัวข้อรวม>
     - **<service>:** สิ่งที่เปลี่ยน
     - **<service>:** สิ่งที่เปลี่ยน

   ห้ามสร้าง entry แยกต่อ service — เขียนสรุปรวมใน entry เดียว
```

### 5.3 Create `INSTRUCTIONS.md` (standalone only)
Migrate classified "project rules" content into the file. Add `<!-- TODO -->` for any standard section that has no content yet:
- `## Directory Structure`
- `## Environment Variables`
- `## Setup`
- `## Testing`
- `## Code Style & Conventions`

### 5.4 Create `services/<name>/AGENTS.md` (monorepo only)
Per service, migrate classified "project rules" content. Add `<!-- TODO -->` for missing sections.

### 5.5 Handle `.agents/` files

**Check which of these files already exist:**
- `.agents/README.md`
- `.agents/workflows/code-factory.md`
- `.agents/workflows/project-doc.md`
- `.agents/workflows/wiki-ingest.md`

**If any exist, ask the user:**

> The following `.agents/` files already exist: [list them].
> How should I handle them?
> 1. **Merge** — keep existing content; add only missing sections (README.md) or missing workflow files (don't overwrite existing ones)
> 2. **Replace** — overwrite with fresh templates (see Supporting File Templates section)
> 3. **Keep** — leave all `.agents/` files untouched

Apply the user's choice:
- **Merge:** For `.agents/README.md`, compare with the template and append only missing sections. For workflows, create only the files that don't exist yet — skip existing ones.
- **Replace:** Overwrite `.agents/README.md` and all 3 workflow files using the Supporting File Templates section.
- **Keep:** Skip all `.agents/` file creation/modification.

**If none of the above files exist** → create all from templates in the Supporting File Templates section without asking.

**Other supporting files (always apply regardless of above choice):**
- **`.agents/config.example.json`** — skip if exists; if creating, use:
  ```json
  {
    "wikiPath": "/path/to/your/claude-vault",
    "agentsPath": "/path/to/.claude/agents",
    "skillsPath": "/path/to/your/global/skills"
  }
  ```
- **Empty directories** — `.agents/agents/`, `.agents/skills/` if they don't exist
- **`CHANGELOG.md`** — create with `# Changelog` header if it doesn't exist (root + per service for monorepo)

### 5.5.5 Import vault skills

**5.5.5.1 — Create default `agentflow-skill`**

Always create `.agents/skills/agentflow-skill/SKILL.md` using the **agentflow-skill Template** at the bottom of this file. This gives the project the ability to import more vault skills on-demand during development.

**5.5.5.2 — Import additional skills from vault**

Check if `skillsPath` exists in `.agents/config.json` (or the existing config):

If `skillsPath` is set:
1. List all directories inside `<skillsPath>` that contain a `SKILL.md`
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

If `skillsPath` is not set → ask the user: "Do you have a vault skills path? If yes, provide it now (e.g. `/path/to/claude-vault/.agents/skills`), or press Enter to skip and run `agentflow-skill` later."

### 5.6 Create or update `CLAUDE.md`

Check if `CLAUDE.md` exists at the project root:

- **If exists** — check whether it already contains `@.agents/config.json`. If not, append the line.
- **If not exists** — create it with these contents (standalone):

  ```markdown
  @AGENTS.md
  @INSTRUCTIONS.md
  @.agents/config.json
  ```

  For monorepo, omit `@INSTRUCTIONS.md`:

  ```markdown
  @AGENTS.md
  @.agents/config.json
  ```

> `@.agents/config.json` ทำให้ Claude รู้ `skillsPath` ตั้งแต่ต้น session และโหลด vault skills ได้ on-demand

### 5.7 Create `.claude` symlink

Create a `.claude` directory symlink pointing to `.agents/` using the Bash tool.

**5.7.1 — Detect OS:**
```bash
uname -s 2>/dev/null || echo "Windows"
```

**5.7.2 — Handle existing `.claude/`:**

- **If symlink already** → skip, report "symlink already exists"
- **If directory** → move files into `.agents/` first, then remove directory:
  ```bash
  # macOS/Linux
  mv .claude/* .agents/ 2>/dev/null; mv .claude/.* .agents/ 2>/dev/null; rmdir .claude
  ```
  ```powershell
  # Windows
  Get-ChildItem -Path .claude -Force | Move-Item -Destination .agents; Remove-Item .claude
  ```
- **If not exists** → proceed

**5.7.3 — Create symlink:**

```bash
ln -s .agents .claude        # macOS/Linux
```
```powershell
New-Item -ItemType SymbolicLink -Path .claude -Target .agents  # Windows
```

> ℹ️ **Windows:** ถ้า command fail ให้แจ้ง user เปิด Developer Mode ก่อน (Settings → System → For developers) เป็นการตั้งค่าครั้งเดียว

Confirm: `.claude → .agents`

## Step 6 — Report

List every file created, backed up, or updated. Then tell the user:

- Verify the migrated files look correct
- Delete `AGENTS.md.bak` once satisfied
- Fill in any remaining `<!-- TODO -->` sections in the generated files
- Run the `.claude` symlink command from Step 5.7 if not done yet
- For monorepo: run `agentflow-add` for any services that don't have a service directory yet

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

## Supporting File Templates

---

### Template: `.agents/README.md`

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

.claude → .agents        # Symlink — lets Claude Code discover agents natively (see agentflow-migrate Step 5.6)

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
