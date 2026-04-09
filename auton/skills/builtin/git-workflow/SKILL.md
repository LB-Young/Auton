---
name: git-workflow
description: "Standardized Git workflow: commit, branch, PR. Use when: (1) user asks about commit messages or branch naming, (2) preparing a PR, (3) reviewing git history, (4) resolving merge conflicts, (5) understanding what changed in a PR. NOT for: GitHub operations (use github skill), initial repo setup."
user-invocable: true
metadata:
  openclaw:
    emoji: "🌿"
---

# Git Workflow Skill

Standardized Git workflow for commits, branches, and pull requests.

## When to Use

✅ **USE when:**
- Writing commit messages
- Creating or managing branches
- Preparing a pull request
- Reviewing git history
- Resolving merge conflicts

❌ **DON'T use when:**
- GitHub operations (issues, PRs, CI) → use `github` skill
- Initial repo setup or git init → use bash directly

## Commit Message Format

```
<type>: <description>

<optional body>
```

**Types:** `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`

**Examples:**
```
feat: add user authentication module
fix: resolve null pointer in login handler
docs: update API documentation
refactor: extract payment processing into service
```

## Branch Naming

```
<type>/<short-description>

# Examples:
feature/user-dashboard
fix/login-redirect
chore/update-deps
hotfix/critical-security-patch
```

## PR Workflow

1. Create feature branch from main
2. Make changes with clear, atomic commits
3. Push and create PR with descriptive title
4. Request review
5. Address feedback with fixup commits
6. Squash and merge

## Conflict Resolution

```bash
# Fetch latest
git fetch origin

# Check for conflicts
git status

# Resolve conflicts in editor
# Then:
git add <resolved-files>
git commit -m "resolve merge conflicts"
```

## Reading History

```bash
# Recent commits
git log --oneline -10

# Changes in last commit
git diff HEAD~1 HEAD

# What changed in a branch
git diff main...feature-branch

# Search commit messages
git log --grep="fix" --oneline
```
