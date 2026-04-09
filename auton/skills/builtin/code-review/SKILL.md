---
name: code-review
description: "Systematic code review: quality, security, patterns. Use when: (1) reviewing PRs or code changes, (2) checking for bugs or security issues, (3) evaluating code quality, (4) suggesting improvements, (5) user says 'review this PR', 'check this code', 'audit'. NOT for: trivial one-line changes, code that user explicitly says is fine, or when reviewing yourself (use another agent)."
user-invocable: true
load-experiences: true
metadata:
  openclaw:
    emoji: "🔍"
---

# Code Review Skill

Systematic review of code changes for quality, security, and best practices.

## When to Use

✅ **USE when:**
- Reviewing pull requests or code changes
- Checking for bugs or security vulnerabilities
- Evaluating code quality
- Suggesting improvements or refactoring
- User says: "review this PR", "check this code", "audit"

❌ **DON'T use when:**
- Trivial one-line changes
- User explicitly says the code is fine
- You wrote the code yourself → ask for another review

## Review Checklist

### Security (Critical — Check First)

- [ ] No hardcoded credentials (API keys, passwords, tokens)
- [ ] All user inputs validated
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention (sanitized HTML)
- [ ] Path traversal checks on file operations
- [ ] Authentication/authorization verified
- [ ] Rate limiting on endpoints
- [ ] Error messages don't leak sensitive data

### Code Quality

- [ ] Readable and well-named
- [ ] Functions are focused (< 50 lines)
- [ ] Files are cohesive (< 800 lines)
- [ ] No deep nesting (> 4 levels)
- [ ] Proper error handling
- [ ] No console.log or debug statements
- [ ] Tests exist for new functionality

### Performance

- [ ] No N+1 queries
- [ ] Missing pagination on large datasets
- [ ] Unbounded queries with constraints
- [ ] Missing caching for expensive operations

### Patterns & Design

- [ ] Follows project conventions
- [ ] Appropriate use of abstractions
- [ ] Not over-engineered for hypothetical future needs
- [ ] Dependencies are justified

## Review Severity Levels

| Level | Meaning | Action |
|-------|---------|--------|
| **CRITICAL** | Security vulnerability or data loss risk | **BLOCK** — Must fix |
| **HIGH** | Bug or significant quality issue | **WARN** — Should fix |
| **MEDIUM** | Maintainability concern | **INFO** — Consider fixing |
| **LOW** | Style or minor suggestion | **NOTE** — Optional |

## PR Review Template

```markdown
## Summary
Brief description of what this PR does.

## Changes
- File 1: What changed
- File 2: What changed

## Security
- [ ] No issues found
- [ ] Issues found (see below)

## Quality
- [ ] No issues found
- [ ] Issues found (see below)

## Recommendations
1. ...
2. ...

## Approval
- **Approve** / **Request Changes** / **Block**
```

## Notes

- Be constructive, not harsh — suggest improvements with reasoning
- Acknowledge good decisions alongside issues
- Prioritize: security > correctness > maintainability > style
- Don't nitpick formatting — use linters for that
