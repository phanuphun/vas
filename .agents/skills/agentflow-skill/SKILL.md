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
