# Agent & Skill Resolution

## Directory Structure

```
.agents/
├── agents/              # Agent definitions (.md files)
├── skills/              # Skills
├── workflows/           # Pipeline documentation
├── config.json          # Machine-specific settings (gitignored — copy from config.example.json)
├── config.example.json  # Config template
└── README.md            # This file
```

## Single Source of Truth

Skills and workflows live in `.agents/`. Agent definitions are loaded from `agentsPath` in `.agents/config.json`. Do not hardcode agent paths.

---

## Agent Loading Protocol (All Tools)

> This protocol applies to **every AI tool** — Claude Code, Cursor, Codex, or any other agent runner. Each tool reads the same source files and interprets them according to its own native conventions. **Do not create new files** — load definitions in-context only.

### Step 1 — Read config

Read `.agents/config.json` and extract:
- `agentsPath` — directory containing agent definition `.md` files
- `wikiPath` — path to the project wiki vault

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
| Feature development | `.agents/workflows/code-factory.md` |
| Wiki ingestion | `.agents/workflows/wiki-ingest.md` |
| Project documentation | `.agents/workflows/project-doc.md` |

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

1. Always read config first — load `agentsPath` and `wikiPath` from `.agents/config.json`
2. Agent definitions: read `agentsPath` from `.agents/config.json` → `<name>.md`
3. Skills: `.agents/skills/<name>/SKILL.md`
4. Workflows: `.agents/workflows/<name>.md`

## Subagent Spawning

Before spawning any multi-agent workflow:

1. Read the relevant workflow file from `.agents/workflows/`
2. Follow workflow steps in order
3. Read agent definitions from `agentsPath` (in `.agents/config.json`) → `<name>.md` before spawning each agent
4. Pass the full agent definition as context to the subagent

For single agent spawning:

- Read the agent definition from `agentsPath` (in `.agents/config.json`) → `<name>.md`
- Pass the full definition as context
- Load skills from `.agents/skills/<name>/SKILL.md` if needed

## Agents

Agent definitions path: read from `.agents/config.json` → `agentsPath`. Do not hardcode paths.

## Wiki

Wiki path: read from `.agents/config.json` → `wikiPath`. Do not hardcode paths.
