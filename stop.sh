#!/bin/bash
PID_FILE="/tmp/cellclaw_bot.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && echo "CellClaw Bot stopped (PID: $PID)"
    else
        echo "Process not found"
    fi
    rm -f "$PID_FILE"
else
    # Fallback: kill all bot.py processes
    pkill -f "python.*bot.py" && echo "Cleaned up all bot.py processes" || echo "No running Bot found"
fi
