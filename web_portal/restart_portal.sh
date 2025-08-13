#!/bin/bash
# Restart the Barbossa Web Portal in tmux

echo "Stopping existing portal..."
# Kill any standalone python processes
pkill -f "web_portal/app.py" 2>/dev/null
# Kill tmux session if it exists
tmux kill-session -t barbossa-portal 2>/dev/null
sleep 2

echo "Starting new portal in tmux session..."
# Change to the web_portal directory and start tmux session with proper command
tmux new-session -d -s barbossa-portal -c ~/barbossa-engineer/web_portal 'python3 app.py'

# Verify the session was created
if tmux has-session -t barbossa-portal 2>/dev/null; then
    echo "Portal started in tmux session 'barbossa-portal'"
else
    echo "Failed to create tmux session. Trying alternative method..."
    cd ~/barbossa-engineer/web_portal
    tmux new-session -d -s barbossa-portal bash -c 'cd ~/barbossa-engineer/web_portal && python3 app.py'
fi

echo "Waiting for portal to be ready..."
# Initial wait for startup
sleep 5
# Give it more time to start up
for i in {1..15}; do
    if curl -k https://localhost:8443/health 2>/dev/null | grep -q "healthy"; then
        echo "✅ Portal is running and healthy!"
        echo "Access at: https://eastindiaonchaincompany.xyz"
        echo "To view logs: tmux attach -t barbossa-portal"
        echo "To detach: Ctrl+B then D"
        
        # Show the process status
        echo ""
        echo "Process status:"
        ps aux | grep "app.py" | grep -v grep | head -1
        exit 0
    fi
    echo -n "."
    sleep 1
done

echo ""
echo "⚠️ Portal may not be responding yet after 10 seconds."
echo "Check logs with: tmux attach -t barbossa-portal"
echo "Check if process is running: ps aux | grep app.py"