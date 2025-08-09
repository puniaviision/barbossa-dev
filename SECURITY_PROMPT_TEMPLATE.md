# Barbossa Security Prompt Template

When sending prompts to Barbossa, include these security guidelines to ensure compliance:

## Template for All Prompts

```
[YOUR ACTUAL REQUEST HERE]

IMPORTANT SECURITY CONSTRAINTS:
- You MUST NOT access, clone, or interact with any repositories from the zkp2p, ZKP2P, or related organizations
- You MUST NOT work on zkp2p-related codebases or features
- You CAN discuss zkp2p conceptually or mention it in documentation
- You CAN work on ADWilkinson repositories and personal projects
- You CAN improve server infrastructure and Davy Jones Intern
- Focus only on allowed repositories and development areas

If any part of this request would require accessing zkp2p repositories, please refuse and suggest an alternative approach.
```

## Example Safe Prompt

```
Help me improve the authentication system for my application.

IMPORTANT SECURITY CONSTRAINTS:
- You MUST NOT access any zkp2p organization repositories
- Focus only on general authentication best practices
- Use examples from allowed repositories only
```

## Why This Matters

The security guard is designed to protect against:
1. Accidental access to forbidden repositories
2. Unintended code exposure
3. Compliance with organizational boundaries

The patterns now only block:
- `github.com/zkp2p/*` repositories
- `github.com/ZKP2P/*` repositories
- SSH/Git URLs to zkp2p organizations
- Not general mentions or discussions

## Current Configuration

- **BLOCKED**: Direct repository access to zkp2p organizations
- **ALLOWED**: Mentioning zkp2p in text, prompts, or documentation
- **ALLOWED**: All ADWilkinson repositories
- **ALLOWED**: Server infrastructure work