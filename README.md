# Barbossa

[![Docker](https://img.shields.io/badge/docker-ghcr.io%2Fadwilkinson%2Fbarbossa--dev-blue?logo=docker)](https://ghcr.io/adwilkinson/barbossa-dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-barbossa.dev-green)](https://barbossa.dev)

**AI engineers that ship code while you sleep.**

Five AI agents discover features, find technical debt, implement changes, review code, and merge PRs—automatically.

```bash
docker pull ghcr.io/adwilkinson/barbossa-dev:latest
```

[Documentation](https://barbossa.dev) · [Quick Start](https://barbossa.dev/quickstart.html)

---

## How It Works

```
Discovery + Product Manager
           ↓
     GitHub Issues (backlog)
           ↓
        Engineer → Pull Request
           ↓
       Tech Lead → Merge/Reject
```

| Agent | Purpose |
|-------|---------|
| **Engineer** | Picks tasks from backlog, creates PRs |
| **Tech Lead** | Reviews PRs, merges or requests changes |
| **Discovery** | Finds TODOs, missing tests, issues |
| **Product Manager** | Proposes high-value features |
| **Auditor** | Monitors system health |

---

## Quick Start

### Requirements

- [Docker](https://docs.docker.com/get-docker/)
- [Claude Max subscription](https://claude.ai) (for Claude Code CLI)
- [GitHub CLI](https://cli.github.com/)

### Setup

```bash
# 1. Authenticate
gh auth login
claude login

# 2. Run install script
curl -fsSL https://raw.githubusercontent.com/ADWilkinson/barbossa-dev/main/install.sh | bash

# 3. Start
cd barbossa && docker compose up -d

# 4. Verify
docker exec barbossa barbossa health
```

The script prompts for your GitHub username and repository, then creates everything for you.

To add more repositories later, edit `config/repositories.json`.

---

## Configuration

Minimal config (`config/repositories.json`):

```json
{
  "owner": "your-github-username",
  "repositories": [
    {
      "name": "my-app",
      "url": "https://github.com/your-github-username/my-app.git"
    }
  ]
}
```

With options:

```json
{
  "owner": "your-github-username",
  "repositories": [
    {
      "name": "my-app",
      "url": "https://github.com/your-github-username/my-app.git",
      "package_manager": "pnpm",
      "do_not_touch": ["src/lib/auth.ts", "prisma/migrations/"]
    }
  ],
  "settings": {
    "telemetry": true,
    "tech_lead": { "auto_merge": true },
    "discovery": { "enabled": true },
    "product_manager": { "enabled": true }
  }
}
```

| Field | Description |
|-------|-------------|
| `package_manager` | `npm`, `yarn`, `pnpm`, or `bun` |
| `do_not_touch` | Files agents should never modify |
| `telemetry` | `true` (default) or `false` to disable analytics |
| `auto_merge` | `true` = merge automatically, `false` = manual review |
| `enabled` | Enable/disable individual agents |

---

## Commands

```bash
docker exec barbossa barbossa health          # Check status
docker exec barbossa barbossa run engineer    # Run now
docker exec barbossa barbossa status          # Activity
docker compose logs -f                        # Logs
```

---

## Troubleshooting

### Claude auth fails
```bash
claude login
docker compose restart
```

### GitHub permission denied
```bash
gh auth login
docker compose restart
```

See [troubleshooting docs](https://barbossa.dev/troubleshooting.html) for more.

---

## Privacy & Telemetry

Barbossa collects anonymous usage data to improve the project:

- **What's collected:** Anonymous installation ID, agent run counts, success rates, version
- **What's NOT collected:** Repository names, code, usernames, or any identifying information

**To opt out**, set in your config:

```json
{
  "settings": {
    "telemetry": false
  }
}
```

Or via environment variable:

```bash
BARBOSSA_ANALYTICS_OPT_OUT=true
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

[MIT](LICENSE)
