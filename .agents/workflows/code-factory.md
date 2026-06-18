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
