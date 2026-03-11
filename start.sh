#!/bin/bash
# OmicsClaw Bot 启动脚本
# 使用 PID 文件防止多开

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="/tmp/omicsclaw_bot.pid"
LOG_FILE="/tmp/omicsclaw_bot.log"

# 检查是否已在运行
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "⚠️  OmicsClaw Bot 已在运行 (PID: $OLD_PID)"
        echo "   使用 ./stop.sh 停止，或 ./restart.sh 重启"
        exit 1
    else
        echo "🧹 清理过期 PID 文件"
        rm -f "$PID_FILE"
    fi
fi

# 加载 .env
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

echo "🚀 启动 OmicsClaw Bot..."
echo "   日志: $LOG_FILE"
echo "   PID 文件: $PID_FILE"

cd "$SCRIPT_DIR"
nohup python3 -u bot.py >> "$LOG_FILE" 2>&1 &
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
