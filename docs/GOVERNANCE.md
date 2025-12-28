# Barbossa Automation Governance

> **Last Updated:** 2025-12-27
> **Status:** Active - All agents must follow these rules

---

## Overview

Barbossa is an autonomous development assistant composed of specialized agents that work together to implement features, fix bugs, and maintain code quality. This document defines how agents behave, interact, and maintain governance standards.

---

## Workflow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. DISCOVERY (Product Manager Agent)                           │
│    - Monitors codebase for issues, technical debt              │
│    - Creates Linear issues in "Backlog" state                  │
│    - Provides context from North Star product vision           │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│ 2. PRIORITIZATION (Human Owner)                                │
│    - Reviews Backlog issues                                    │
│    - Moves priority items to "To-Do" state                     │
│    - Agent work ONLY happens on "To-Do" issues                 │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│ 3. IMPLEMENTATION (Engineer Agent)                             │
│    - Pulls ONLY from "To-Do" issues (never Backlog)            │
│    - Implements exactly what's requested                       │
│    - Writes tests for bug fixes (mandatory)                    │
│    - Creates PR with "MUS-XX: Title" format                    │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│ 4. REVIEW (Tech Lead Agent)                                    │
│    - Validates Linear issue exists and was in To-Do            │
│    - Reviews code quality and tests                            │
│    - Auto-rejects invalid PRs                                  │
│    - Auto-merges approved PRs                                  │
│    - Updates Linear issue to "Done"                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Agent Roles & Responsibilities

### 1. Product Manager Agent

**Schedule:** 3x daily (8 AM, 2 PM, 8 PM)

**Responsibilities:**
- Discover work opportunities (bugs, tech debt, improvements)
- Create well-documented Linear issues
- Add issues to **Backlog** state only
- Provide product context from North Star document

**Constraints:**
- NEVER move issues to To-Do (human-only operation)
- NEVER create PRs directly
- Issues must include: problem statement, proposed solution, affected files
- Must reference product vision when relevant

**Output Format:**
```
Issue Title: [Bug|Feature|Improvement]: Clear description
State: Backlog
Labels: [bug|feature|improvement], [ios|web|backend]
Description:
  ## Problem
  ## Proposed Solution
  ## Files Affected
  ## Additional Context
```

---

### 2. Engineer Agent

**Schedule:** Every hour (on the hour)

**Responsibilities:**
- Pull work ONLY from "To-Do" issues
- Implement exactly what's requested (no scope creep)
- Write tests for all bug fixes
- Create PRs with proper Linear issue references

**CRITICAL CONSTRAINTS:**

#### Work Source Rules
```
✓ ONLY work on issues in "To-Do" state
✗ NEVER work on "Backlog" issues
✗ NEVER self-discover work
✗ NEVER invent features

If To-Do is empty:
  → Output: "NO_TODO_ISSUES: Waiting for prioritization"
  → EXIT immediately
```

#### PR Requirements
```
Title Format: "MUS-XX: Description"
  - MUS-XX MUST be a real Linear issue
  - Issue MUST have been in "To-Do" state
  - Fake issue IDs will be AUTO-REJECTED

Branch Naming: "barbossa/mus-XX-description"
  - Auto-links to Linear issue
```

#### Test Requirements
```
MANDATORY for bug fixes:
  1. Write test that reproduces the bug (fails before fix)
  2. Implement the fix
  3. Verify test passes
  4. Include test in PR

MANDATORY for >30 lines of business logic:
  - Add unit tests for new functionality
  - Follow existing test patterns (XCTest for iOS)
```

**Anti-Patterns (Will Fail Review):**
- Over-engineering simple fixes
- Adding features beyond the issue scope
- Refactoring unrelated code
- Missing tests for bug fixes
- Working on non-To-Do issues

---

### 3. Tech Lead Agent

**Schedule:** Every hour at :35 (e.g., 12:35, 1:35)

**Responsibilities:**
- Validate Linear issue references (not just format)
- Review code quality and architecture
- Enforce test requirements
- Auto-merge approved PRs
- Update Linear issues to "Done"

**Validation Steps:**

#### 1. Linear Issue Validation (CRITICAL)
```python
def validate_pr(pr_title):
    # Extract issue ID (e.g., "MUS-123: Fix bug" → "MUS-123")
    issue_id = extract_issue_id(pr_title)

    # Check 1: Issue ID exists in title?
    if not issue_id:
        return CLOSE("No Linear issue reference")

    # Check 2: Issue actually exists in Linear?
    issue = linear_api.get_issue(issue_id)
    if not issue:
        return CLOSE(f"{issue_id} does not exist")

    # Check 3: Was issue in "To-Do" state?
    if issue.state.name == "Backlog":
        return CLOSE(f"{issue_id} is in Backlog, not To-Do")

    # Passed validation
    return APPROVE_FOR_REVIEW
```

#### 2. Code Quality Review
```
✓ Changes match issue description
✓ No scope creep or bonus features
✓ Tests included for bug fixes
✓ No obvious security issues
✓ Follows existing patterns
```

#### 3. Auto-Decisions
```
AUTO-CLOSE conditions:
  - No Linear issue reference
  - Fake/non-existent Linear issue
  - Issue was in Backlog (not To-Do)
  - No tests for bug fix
  - Major security vulnerability

AUTO-MERGE conditions:
  - Valid Linear issue (existed in To-Do)
  - Code quality acceptable
  - Tests present and passing
  - No scope creep
```

#### 4. Post-Merge Actions
```
After successful merge:
  1. Update Linear issue state → "Done"
  2. Close PR
  3. Delete branch (if safe)
```

---

## Linear Integration

### States & Workflow

| State | Owner | Purpose |
|-------|-------|---------|
| **Backlog** | Product Manager | Suggested work, awaiting prioritization |
| **To-Do** | Human Owner | Prioritized work, ready for Engineer |
| **In Progress** | Engineer | Work actively being implemented |
| **Done** | Tech Lead | Merged and completed |

### Critical Rules

1. **Backlog ≠ To-Do**
   - Backlog = PM's staging area
   - To-Do = Human-approved priorities
   - Engineer ONLY touches To-Do

2. **Human-Only Operations**
   - Moving Backlog → To-Do
   - Closing/archiving issues
   - Changing priorities

3. **Agent-Only Operations**
   - Creating issues (PM only)
   - Moving To-Do → In Progress (Engineer)
   - Moving In Progress → Done (Tech Lead)

### Issue Format

```markdown
Title: [Type]: Clear, actionable description

Labels:
  - Type: bug, feature, improvement
  - Area: ios, web, backend
  - Optional: priority-high, needs-discussion

Description:
## Problem
[What's broken or missing?]

## Solution
[How to fix it]

## Files
- path/to/file1.swift
- path/to/file2.swift

## Testing
[How to verify the fix]
```

---

## Testing Requirements

### When Tests Are Mandatory

| Scenario | Test Required | Type |
|----------|---------------|------|
| Bug fix | ✅ ALWAYS | Regression test |
| New feature (>30 LOC) | ✅ ALWAYS | Unit/integration tests |
| Refactoring | ✅ If logic changes | Unit tests |
| Test infrastructure | ✅ If improves coverage | Infrastructure |
| Documentation only | ❌ Not required | N/A |
| UI-only changes | ⚠️ If testable | UI tests (future) |

### Test-Only PRs (ACCEPTABLE)

Test-only PRs are **valid and encouraged** for improving test suite quality:

**Acceptable Test-Only PR Scenarios:**
- ✅ Adding regression tests for fixed bugs (preventing recurrence)
- ✅ Improving coverage for existing features (integration, E2E tests)
- ✅ Expanding test infrastructure (mocks, helpers, utilities)
- ✅ Adding smoke tests for critical user flows
- ✅ Fixing flaky tests or improving test reliability

**Requirements:**
- Must reference a Linear issue (same as all PRs)
- Linear issue must explicitly request test infrastructure work
- Must explain what coverage gap is being filled
- Must follow existing test patterns
- Should not refactor production code (test-only)

**Example Valid Issues:**
- "Add integration tests for drop opening flow"
- "Add regression test for MUS-19 sellback bug"
- "Create MockContentStore for integration testing"
- "Add smoke tests for critical path (open, add, ship)"

**Note:** Test-only PRs are infrastructure improvements, not scope creep. The key distinction is that test work must be REQUESTED in a Linear issue, not self-discovered by the engineer.

---

### Test Patterns by Platform

**iOS (XCTest):**
```swift
// File: MuseTests/UserStoreTests.swift
import XCTest
@testable import Muse

final class UserStoreTests: XCTestCase {
    func testBugFix_CreditsAddedOnSellback() {
        // Setup
        let store = UserStore()
        let initialBalance = store.creditBalance

        // Test that reproduces the bug
        store.sellProductForCredits(value: 1000)

        // Verify fix
        XCTAssertEqual(store.creditBalance, initialBalance + 1000,
                      "Credits should increase after sellback")
    }
}
```

**Backend (Python):**
```python
# File: tests/test_user_service.py
def test_bug_fix_credits_persist():
    """Regression test for sellback credit bug"""
    user = create_test_user()
    initial = user.credit_balance

    # Reproduce the bug
    user.sellback_product(credit_value=1000)

    # Verify fix
    assert user.credit_balance == initial + 1000
```

---

## PR Standards

### Title Format
```
MUS-XX: Clear description of change

Examples:
✓ MUS-19: Fix sellback credits not being added
✓ MUS-20: Add haptic feedback to drop reveal
✗ Fix bug (no issue reference)
✗ MUS-999: Made up feature (fake issue)
```

### Branch Naming
```
barbossa/mus-XX-kebab-case-description

Examples:
✓ barbossa/mus-19-fix-sellback-credits
✓ barbossa/mus-20-add-haptic-feedback
✗ feature/new-thing (no issue reference)
```

### PR Description
```markdown
## Issue
Fixes MUS-XX

## Changes
- [Concise bullet points of what changed]

## Testing
- [How you tested this]
- [Automated tests added]

## Notes
[Any important context for reviewer]

🤖 Created by Barbossa Engineer Agent
Powered by [Claude Code](https://claude.com/claude-code)
```

### PR Footer (REQUIRED)

All Barbossa agent PRs MUST include this footer at the end of the PR description:

```markdown
🤖 Created by Barbossa Engineer Agent
Powered by [Claude Code](https://claude.com/claude-code)
```

**Purpose:** Distinguishes Barbossa agent PRs from human-created or Claude Code-assisted PRs in GitHub PR lists.

**Variants:**
- Engineer Agent: `🤖 Created by Barbossa Engineer Agent`
- Tech Lead Agent: `🤖 Created by Barbossa Tech Lead Agent`
- Product Manager Agent: `🤖 Created by Barbossa Product Manager Agent`

---

## Anti-Patterns & Auto-Reject

### Immediate Rejection Triggers

| Pattern | Why | Action |
|---------|-----|--------|
| No Linear issue | Violates governance | CLOSE with comment |
| Fake issue ID | Circumvents validation | CLOSE with warning |
| Backlog issue | Bypasses prioritization | CLOSE, explain workflow |
| No tests (bug fix) | Quality standard | CLOSE, request tests |
| Scope creep | Undermines trust | CLOSE, split into issues |
| Security issue | Risk to production | CLOSE, flag for review |

### Warning Signs (Human Review)

- Large refactoring (>200 lines changed)
- Changes to critical files (auth, payments, database)
- New dependencies added
- Breaking API changes

---

## Configuration Reference

### Barbossa Config (`repositories.json`)
```json
{
  "issue_tracker": {
    "type": "linear",
    "linear": {
      "team_key": "MUS",
      "backlog_state": "Backlog"
    }
  },
  "settings": {
    "tech_lead": {
      "auto_merge": true,
      "require_tests_for_bugs": true
    },
    "engineer": {
      "require_tests_with_bugfixes": true,
      "min_lines_for_tests": 30
    },
    "schedule": {
      "engineer": "every_hour",
      "tech_lead": "35 * * * *",
      "product_manager": "3x_daily"
    }
  }
}
```

### Prompt Files
- `/prompts/engineer.txt` - Engineer agent constraints
- `/prompts/tech_lead.txt` - Tech Lead validation rules
- `/prompts/product_manager.txt` - PM discovery guidelines

---

## Documentation Maintenance

### Critical Documentation Files

These files must be kept in sync with implementation changes:

| Document | Location | Update Trigger | Responsibility |
|----------|----------|----------------|----------------|
| **USER_FLOWS.md** | `/Users/punia/Projects/Muse/muse/docs/USER_FLOWS.md` | Feature additions (payments, shipping, new flows) | Engineer Agent + Human Review |
| **north-star.md** | `/Users/punia/Projects/Muse/muse/docs/north-star.md` | Product vision changes | Human only |
| **CLAUDE.md** | `/Users/punia/Projects/Muse/CLAUDE.md` | Tech stack changes, architecture shifts | Engineer Agent |
| **GOVERNANCE.md** | `/Users/punia/Projects/barbossa-dev/docs/GOVERNANCE.md` | Workflow rule changes | Human only |

### When to Update USER_FLOWS.md

**MUST update when implementing:**
- New user-facing features (payments, shipping, notifications)
- New external API integrations (Stripe, shipping providers)
- Changes to core flows (authentication, drop opening, collection management)
- New database tables or schema changes
- New analytics events
- Changes to product tiers or probabilities

**Process:**
1. Engineer implements feature in code
2. Engineer updates USER_FLOWS.md with:
   - New user actions
   - Architecture flow with file references
   - Edge cases for the new feature
   - Database schema changes
   - Analytics events
3. Include documentation update in the same PR
4. Tech Lead validates documentation is updated during review

**Example PR checklist:**
```markdown
## Changes
- [x] Implemented Stripe payment integration
- [x] Updated USER_FLOWS.md with payment flow
- [x] Added edge cases (payment failures, refunds)
- [x] Documented new environment variables
```

### Documentation Debt

If a feature ships without documentation updates:
1. Tech Lead creates a Linear issue: "Update USER_FLOWS.md for [feature]"
2. Issue goes to Backlog with "documentation" label
3. Must be completed before next related feature

---

## Troubleshooting

### Issue: Engineer working on Backlog items
**Fix:** Check `barbossa_engineer.py` line 263:
```python
# WRONG
tracker.get_issues_context(state="Backlog", limit=5)

# CORRECT
tracker.get_issues_context(state="To-Do", limit=5)
```

### Issue: PRs merged without Linear validation
**Fix:** Check `barbossa_tech_lead.py` has `_validate_linear_issue()` call before review

### Issue: Linear MCP timeouts
**Fix:** Switch to local MCP in `.mcp.json`:
```json
"linear": {
  "command": "npx",
  "args": ["-y", "mcp-linear"],
  "env": {"LINEAR_API_KEY": "lin_api_xxx"}
}
```

---

## Audit Checklist

Run this audit monthly to ensure governance compliance:

**Workflow:**
- [ ] PM creates issues in Backlog only
- [ ] Engineer queries To-Do state (not Backlog)
- [ ] Tech Lead validates Linear issues exist
- [ ] Tests required for bug fixes
- [ ] PR titles match format
- [ ] Linear issues auto-updated to Done
- [ ] No fake issue IDs merged
- [ ] Backlog items not worked on

**Documentation:**
- [ ] USER_FLOWS.md updated when features ship
- [ ] No documentation debt in Linear
- [ ] CLAUDE.md reflects current tech stack
- [ ] GOVERNANCE.md rules match agent behavior

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-27 | Initial governance framework |
| 1.1 | 2025-12-27 | Added Linear validation, test requirements |
| 1.2 | 2025-12-27 | Added documentation maintenance requirements |
| 1.3 | 2025-12-28 | Added required PR footer to identify Barbossa agent work |
| 1.4 | 2025-12-28 | Added nuanced test-only PR rules (acceptable when explicitly requested in Linear) |

---

## References

- Linear API: https://developers.linear.app/docs/graphql/working-with-the-graphql-api
- Barbossa Repo: `/Users/punia/Projects/barbossa-dev`
- Muse Repo: `/Users/punia/Projects/Muse/muse`
- North Star: `/Users/punia/Projects/Muse/muse/docs/north-star.md`
