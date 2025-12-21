# FAQ

### What is Barbossa?

AI agents that work on your code while you sleep. They find issues, implement fixes, create PRs, and review each other's work.

### Is it free?

Yes. You need a Claude Max subscription from Anthropic.

### Will it break my code?

By default, approved PRs are merged automatically. Set `auto_merge: false` in config if you want to review and merge manually.

### Can I trust it with private repos?

Code stays on your machine and GitHub. Claude sees code for analysis (same as using Claude directly).

### What if it creates a bad PR?

Close it. Barbossa moves on.

### Can I pause it?

```bash
docker compose stop    # Pause
docker compose start   # Resume
```

### How do I improve quality?

Add a `CLAUDE.md` to your repo with project context.

### Claude auth fails?

```bash
claude login
docker compose restart
```

### GitHub permission denied?

```bash
gh auth login
docker compose restart
```

### No PRs being created?

1. Check for issues with `backlog` label
2. Run manually: `docker exec barbossa barbossa run engineer`
3. Check logs: `docker exec barbossa barbossa logs engineer`
