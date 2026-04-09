---
name: skill-creator
description: "Create, edit, or improve AgentSkills. Use when: (1) user wants to create a new skill, (2) improve or audit an existing skill, (3) user says 'create a skill', 'build a skill', 'author a skill'. NOT for: simple questions about skills that can be answered directly, or when skill already exists and user just wants to use it."
user-invocable: true
load-experiences: true
metadata:
  openclaw:
    emoji: "🛠️"
---

# Skill Creator

Create, edit, or improve skills that extend Auton's capabilities with specialized knowledge and workflows.

## What Skills Provide

1. **Specialized workflows** — Multi-step procedures for specific domains
2. **Tool integrations** — Instructions for working with specific file formats or APIs
3. **Domain expertise** — Company-specific knowledge, schemas, business logic
4. **Bundled resources** — Scripts, references, and assets for complex tasks

## When to Use This Skill

✅ **USE when:**
- User asks to create a new skill for a specific domain
- User wants to improve or tidy up an existing skill
- User wants to audit a skill for completeness
- User says: "create a skill", "build a skill", "author a skill", "improve this skill"

❌ **DON'T use when:**
- Simple questions about what skills exist → use `/skill list`
- User just wants to know about a specific skill → use `/skill info <name>`
- Installing a .skill package → use `/skill install <file>`

## Skill Anatomy

Every skill is a directory:

```
<skill-name>/
├── SKILL.md          # Required: YAML frontmatter + Markdown body
├── scripts/          # Optional: Executable scripts (run directly, not in context)
├── references/        # Optional: Reference docs (loaded on demand)
├── assets/           # Optional: Output assets (templates, images)
└── experiences/      # Optional: Usage lessons learned
    └── README.md     # Experience entries
```

## SKILL.md Format

```yaml
---
name: <skill-name>
description: "What this skill does and when to use it. Be specific about triggers."
user-invocable: true       # Allow /skill <name> invocation
load-experiences: true     # Auto-load experiences/README.md
metadata:
  openclaw:
    emoji: "🔧"
    requires:
      bins: ["gh", "jq"]   # Required binaries
---

# Skill Name

## When to Use

✅ **USE when:** ...
❌ **DON'T use when:** ...

## Quick Start

```bash
# Example command
```

## Common Patterns

...
```

## Skill Creation Process

1. **Understand the use case** — Get concrete examples of how the skill will be used
2. **Plan resources** — Determine which of scripts/references/assets/experiences are needed
3. **Initialize directory** — Create `~/.auton/skills/<skill-name>/`
4. **Write SKILL.md** — Fill in frontmatter and body
5. **Create experiences/README.md** — Set up lessons tracking
6. **Package (optional)** — Create `.skill` package for distribution

## Naming Conventions

- Lowercase letters, digits, and hyphens only
- Under 64 characters
- Prefer verb-led names: `postgres-manager`, `github-review`, `api-debugger`
- Namespace by tool when helpful: `gh-address-comments`

## Key Principles

- **Concise over verbose** — Only add what the model doesn't already know
- **Progressive disclosure** — SKILL.md body is loaded after trigger; keep it lean
- **Experience tracking** — `experiences/README.md` records lessons to avoid repeating mistakes
- **References on demand** — Put detailed docs in `references/`, not in SKILL.md body
