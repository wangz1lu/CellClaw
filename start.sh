#!/bin/bash
# CellClaw Bot Startup Script
# Uses PID file to prevent multiple instances

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="/tmp/cellclaw_bot.pid"
LOG_FILE="/tmp/cellclaw_bot.log"
VENV_DIR="$SCRIPT_DIR/venv"

# Check if already running
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "CellClaw Bot is already running (PID: $OLD_PID)"
        echo "Use ./stop.sh to stop, or ./restart.sh to restart"
        exit 1
    else
        echo "Cleaning up stale PID file"
        rm -f "$PID_FILE"
    fi
fi

# Select Python: prefer venv
if [ -f "$VENV_DIR/bin/python3" ]; then
    PYTHON="$VENV_DIR/bin/python3"
    echo "Using venv: $VENV_DIR"
elif [ -f "$VENV_DIR/bin/python" ]; then
    PYTHON="$VENV_DIR/bin/python"
    echo "Using venv: $VENV_DIR"
else
    echo "WARNING: venv not found, using system Python (run bash install.sh first)"
    PYTHON="python3"
fi

# Check if discord module is available, install if not
if ! "$PYTHON" -c "import discord" 2>/dev/null; then
    echo "Installing dependencies..."
    "$PYTHON" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"
fi

# Check again
if ! "$PYTHON" -c "import discord" 2>/dev/null; then
    echo "ERROR: Failed to install dependencies. Run: bash install.sh"
    exit 1
fi

# Load .env
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
else
    echo "ERROR: .env not found. Run: bash install.sh"
    exit 1
fi

echo "Starting CellClaw Bot..."
echo "   Log: $LOG_FILE"
echo "   PID File: $PID_FILE"

cd "$SCRIPT_DIR"
nohup "$PYTHON" -u bot.py >> "$LOG_FILE" 2>&1 &
BOT_PID=$!
echo $BOT_PID > "$PID_FILE"

sleep 5
if kill -0 "$BOT_PID" 2>/dev/null; then
    echo "Bot started successfully (PID: $BOT_PID)"
    tail -3 "$LOG_FILE"
else
    echo "Bot failed to start, check log:"
    tail -10 "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi

# Start Dashboard HTTP server
echo "Starting Dashboard HTTP server..."
nohup "$PYTHON" -c "
import http.server
import socketserver
import json
import urllib.request
PORT = 7860
API_PORT = 19766

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/'):
            endpoint = self.path[4:]
            url = f'http://127.0.0.1:{API_PORT}{endpoint}'
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=10) as r:
                    self.send_response(r.status)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(r.read())
            except:
                self.send_response(500)
                self.end_headers()
        else:
            self.path = '/dashboard.html'
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
    
    def do_POST(self):
        if self.path == '/api/chat':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            url = f'http://127.0.0.1:{API_PORT}/chat'
            try:
                req = urllib.request.Request(url, data=body, method='POST')
                req.add_header('Content-Type', 'application/json')
                with urllib.request.urlopen(req, timeout=60) as r:
                    self.send_response(r.status)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(r.read())
            except:
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

print(f'Dashboard: http://127.0.0.1:{PORT}')
with socketserver.TCPServer(('', PORT), Handler) as httpd:
    httpd.serve_forever()
" > /tmp/cellclaw_dashboard.log 2>&1 &

echo "Dashboard started (http://127.0.0.1:7860)"
