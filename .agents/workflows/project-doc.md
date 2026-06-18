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
