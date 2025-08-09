#!/bin/bash
# Restart the Barbossa Web Portal in tmux

echo "Stopping existing portal..."
# Kill any standalone python processes
pkill -f "web_portal/app.py" 2>/dev/null
# Kill tmux session if it exists
tmux kill-session -t barbossa-portal 2>/dev/null
sleep 2

echo "Starting new portal in tmux session..."
cd ~/barbossa-engineer/web_portal
tmux new-session -d -s barbossa-portal 'python3 app.py'
echo "Portal started in tmux session 'barbossa-portal'"

echo "Waiting for portal to be ready..."
sleep 3

# Test if it's responding
if curl -k https://localhost:8443/health 2>/dev/null | grep -q "healthy"; then
    echo "✅ Portal is running and healthy!"
    echo "Access at: https://eastindiaonchaincompany.xyz"
    echo "To view logs: tmux attach -t barbossa-portal"
    echo "To detach: Ctrl+B then D"
else
    echo "⚠️ Portal may not be responding yet."
    echo "Check logs with: tmux attach -t barbossa-portal"
fi