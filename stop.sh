#!/bin/bash
PID_FILE="/tmp/omicsclaw_bot.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" && echo "✅ OmicsClaw Bot 已停止 (PID: $PID)"
    else
        echo "⚠️  进程不存在"
    fi
    rm -f "$PID_FILE"
else
    # 兜底：杀掉所有 bot.py 进程
    pkill -f "python.*bot.py" && echo "✅ 已清理所有 bot.py 进程" || echo "⚠️  没有运行中的 Bot"
fi
