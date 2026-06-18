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
