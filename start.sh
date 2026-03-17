#!/bin/bash
# CellClaw Bot 启动脚本
# 使用 PID 文件防止多开

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="/tmp/cellclaw_bot.pid"
LOG_FILE="/tmp/cellclaw_bot.log"
VENV_DIR="$SCRIPT_DIR/venv"

# 检查是否已在运行
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "⚠️  CellClaw Bot 已在运行 (PID: $OLD_PID)"
        echo "   使用 ./stop.sh 停止，或 ./restart.sh 重启"
        exit 1
    else
        echo "🧹 清理过期 PID 文件"
        rm -f "$PID_FILE"
    fi
fi

# 选择 Python 解释器：优先使用 venv
if [ -f "$VENV_DIR/bin/python3" ]; then
    PYTHON="$VENV_DIR/bin/python3"
    echo "   使用虚拟环境: $VENV_DIR"
elif [ -f "$VENV_DIR/bin/python" ]; then
    PYTHON="$VENV_DIR/bin/python"
    echo "   使用虚拟环境: $VENV_DIR"
else
    echo "⚠️  未找到 venv，使用系统 Python（建议先运行 bash install.sh）"
    PYTHON="python3"
fi

# 检查 discord 模块是否可用，如果没有则自动安装
if ! "$PYTHON" -c "import discord" 2>/dev/null; then
    echo "📦 缺少依赖，正在自动安装..."
    "$PYTHON" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"
fi

# 再次检查
if ! "$PYTHON" -c "import discord" 2>/dev/null; then
    echo "❌ 依赖安装失败，请手动运行: bash install.sh"
    exit 1
fi

# 加载 .env
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
else
    echo "❌ 未找到 .env 配置文件，请先运行: bash install.sh"
    exit 1
fi

echo "🚀 启动 CellClaw Bot..."
echo "   日志: $LOG_FILE"
echo "   PID 文件: $PID_FILE"

cd "$SCRIPT_DIR"
nohup "$PYTHON" -u bot.py >> "$LOG_FILE" 2>&1 &
BOT_PID=$!
echo $BOT_PID > "$PID_FILE"

sleep 5
if kill -0 "$BOT_PID" 2>/dev/null; then
    echo "✅ Bot 启动成功 (PID: $BOT_PID)"
    tail -3 "$LOG_FILE"
else
    echo "❌ Bot 启动失败，查看日志:"
    tail -10 "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi


# 启动 Dashboard HTTP 服务器
echo "🚀 启动 Dashboard HTTP 服务器..."
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

print(f'🧬 Dashboard: http://127.0.0.1:{PORT}')
with socketserver.TCPServer(('', PORT), Handler) as httpd:
    httpd.serve_forever()
" > /tmp/omicsclaw_dashboard.log 2>&1 &

echo "✅ Dashboard 已启动 (http://127.0.0.1:7860)"
