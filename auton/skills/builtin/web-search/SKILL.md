---
name: web-search
description: "Web search and content fetching. Use when: (1) user asks for current information not in training data, (2) looking up documentation, (3) finding answers to factual questions, (4) searching for code examples or tutorials. NOT for: reading local files, accessing authenticated/internal resources, or when user explicitly asks to use a specific tool."
user-invocable: true
metadata:
  openclaw:
    emoji: "🔍"
---

# Web Search Skill

Use web search and fetching to find current information, documentation, and code examples.

## When to Use

✅ **USE when:**
- User asks for information not in training data
- Looking up current documentation or API references
- Finding code examples or tutorials
- Researching a topic before implementation
- Verifying if something is current best practice

❌ **DON'T use when:**
- Reading local files → use `read` tool directly
- User provides a specific URL → use `web_fetch` tool
- Context already has the answer → just answer directly

## Workflow

1. **Search** — Use `web_search` for broad discovery
2. **Fetch** — Use `web_fetch` to get full content from relevant URLs
3. **Synthesize** — Summarize findings and cite sources

## Search Tips

- Be specific: `python httpx async tutorial` not just `python`
- Include context: `anthropic claude api python streaming`
- Use quotes for exact matches: `"exact phrase"`
- Filter by date when needed: `site:github.com react 2024`

## Content Fetching

After finding relevant URLs:
1. Fetch the full page with `web_fetch`
2. Extract relevant sections
3. Cite the source URL in your response

## Quality Signals

Prioritize:
- Official documentation (docs.example.com)
- GitHub READMEs from reputable projects
- Stack Overflow answers with high votes
- Tutorial sites from known authors

Be cautious with:
- Blog posts from unknown authors
- Outdated content (check dates)
- Unofficial API wrappers
