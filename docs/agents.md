# Agents

Five autonomous agents work on your codebase.

---

## Overview

| Agent | Purpose |
|-------|---------|
| **Engineer** | Picks tasks from backlog, creates PRs |
| **Tech Lead** | Reviews PRs, merges or requests changes |
| **Discovery** | Finds TODOs, missing tests, issues |
| **Product Manager** | Proposes high-value features |
| **Auditor** | Monitors system health |

---

## Pipeline

```
Discovery + Product Manager
           ↓
     GitHub Issues (backlog)
           ↓
        Engineer → Pull Request
           ↓
       Tech Lead → Merge/Reject
```

---

## How Each Agent Works

### Engineer
Picks tasks from the GitHub Issues backlog and implements them.
- Finds issues labeled `backlog`
- Implements the fix/feature
- Creates a pull request
- Links PR to issue with `Closes #XX`

### Tech Lead
Reviews pull requests and decides whether to merge or request changes.
- Checks CI status (must pass)
- Reviews code quality
- Merges good PRs automatically (default behavior)
- Requests changes on weak PRs
- Set `auto_merge: false` in config to require manual merges

### Discovery
Scans the codebase for technical debt and creates GitHub Issues.
- TODO and FIXME comments
- Missing tests
- Accessibility issues

### Product Manager
Analyzes the codebase and proposes high-value features.
- Reads CLAUDE.md to understand the product
- Creates feature issues with acceptance criteria

### Auditor
Monitors system health and identifies patterns.
- Analyzes agent logs
- Tracks PR outcomes

---

## Run Manually

```bash
docker exec barbossa barbossa run engineer
docker exec barbossa barbossa run tech-lead
docker exec barbossa barbossa run discovery
```
