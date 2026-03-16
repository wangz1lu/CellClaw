#!/usr/bin/env python3
"""
OmicsClaw Dashboard
A Gradio-based dashboard for monitoring and controlling OmicsClaw
"""

import asyncio
import logging
import os
import threading
import time
from pathlib import Path
from typing import List, Dict, Any

import gradio as gr
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("omicsclaw.dashboard")

# Configuration
API_PORT = 18766
WS_PORT = 18765
DASHBOARD_PORT = 7860

# Global state
API_BASE = f"http://127.0.0.1:{API_PORT}"
current_user_id = "dashboard_user"

# =====================
# CSS Styles
# =====================

CSS = """
/* OmicsClaw Dashboard - Minimal Gray + Gene Blue */
:root {
    --bg-primary: #FFFFFF;
    --bg-secondary: #F8F9FA;
    --bg-sidebar: #F1F3F5;
    --text-primary: #212529;
    --text-secondary: #495057;
    --accent-blue: #0D6EFD;
    --accent-light: #E7F1FF;
    --success: #198754;
    --warning: #FFC107;
    --danger: #DC3545;
    --border: #DEE2E6;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

#sidebar {
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border);
    padding: 20px;
}

#header {
    background: var(--bg-primary);
    border-bottom: 1px solid var(--border);
    padding: 15px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

#title {
    font-size: 20px;
    font-weight: 600;
    color: var(--text-primary);
}

#status-bar {
    background: var(--bg-secondary);
    padding: 10px 20px;
    border-bottom: 1px solid var(--border);
    display: flex;
    gap: 30px;
}

.status-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    color: var(--text-secondary);
}

.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
}

.status-dot.online { background: var(--success); }
.status-dot.offline { background: var(--danger); }
.status-dot.running { background: var(--accent-blue); }

.menu-item {
    padding: 12px 15px;
    margin: 5px 0;
    border-radius: 8px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 12px;
    color: var(--text-secondary);
    transition: all 0.2s;
}

.menu-item:hover {
    background: var(--bg-primary);
    color: var(--text-primary);
}

.menu-item.active {
    background: var(--accent-light);
    color: var(--accent-blue);
    font-weight: 500;
}

.menu-icon {
    font-size: 18px;
}

.gr-button.primary {
    background: var(--accent-blue) !important;
    border: none !important;
}

.gr-button.primary:hover {
    background: #0B5ED7 !important;
}

/* Tables */
table {
    width: 100%;
    border-collapse: collapse;
}

th, td {
    padding: 12px 15px;
    text-align: left;
    border-bottom: 1px solid var(--border);
}

th {
    background: var(--bg-secondary);
    font-weight: 600;
    color: var(--text-secondary);
    font-size: 12px;
    text-transform: uppercase;
}

tr:hover {
    background: var(--bg-secondary);
}

/* Status badges */
.badge {
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
}

.badge.success { background: #D1E7DD; color: #0F5132; }
.badge.warning { background: #FFF3CD; color: #664D03; }
.badge.danger { background: #F8D7DA; color: #842029; }
.badge.info { background: var(--accent-light); color: var(--accent-blue); }
"""

# =====================
# Helper Functions
# =====================

def api_get(endpoint: str) -> dict:
    """Make GET request to API"""
    try:
        resp = requests.get(f"{API_BASE}{endpoint}", timeout=5)
        return resp.json()
    except Exception as e:
        logger.error(f"API error: {e}")
        return {"error": str(e)}


def api_post(endpoint: str, data: dict) -> dict:
    """Make POST request to API"""
    try:
        resp = requests.post(f"{API_BASE}{endpoint}", json=data, timeout=30)
        return resp.json()
    except Exception as e:
        logger.error(f"API error: {e}")
        return {"error": str(e)}


def get_servers() -> List[Dict]:
    """Get server list"""
    result = api_get("/servers")
    if isinstance(result, list):
        return result
    return []


def get_jobs() -> List[Dict]:
    """Get job list"""
    result = api_get("/jobs")
    if isinstance(result, list):
        return result
    return []


def get_stats() -> Dict:
    """Get overall stats"""
    return api_get("/stats")


def get_chat_history(limit: int = 50) -> List[Dict]:
    """Get chat history"""
    result = api_get(f"/sessions/{current_user_id}/history?limit={limit}")
    if isinstance(result, dict):
        return result.get("messages", [])
    return []


def send_chat_message(message: str) -> str:
    """Send chat message"""
    if not message.strip():
        return ""
    
    result = api_post("/chat", {"message": message, "user_id": current_user_id})
    
    if "error" in result:
        return f"❌ Error: {result['error']}"
    
    return result.get("text", "✅ Message sent")


# =====================
# Page Components
# =====================

def render_status_bar():
    """Render top status bar"""
    stats = get_stats()
    
    servers_online = stats.get("servers_online", 0)
    servers_total = stats.get("servers", 0)
    jobs_running = stats.get("jobs_running", 0)
    jobs_total = stats.get("jobs", 0)
    
    return f"""
    <div id="status-bar">
        <div class="status-item">
            <span class="status-dot {'online' if servers_online > 0 else 'offline'}"></span>
            <span>🖥️ {servers_online}/{servers_total} Servers Online</span>
        </div>
        <div class="status-item">
            <span class="status-dot {'running' if jobs_running > 0 else 'offline'}"></span>
            <span>📊 {jobs_running}/{jobs_total} Tasks Running</span>
        </div>
        <div class="status-item">
            <span>🔄 Last updated: {time.strftime('%H:%M:%S')}</span>
        </div>
    </div>
    """


def page_servers():
    """Servers page"""
    servers = get_servers()
    
    html = """
    <h2>🖥️ 服务器管理</h2>
    <p>监控远程服务器连接状态</p>
    """
    
    if not servers:
        html += "<p>暂无服务器配置</p>"
    else:
        html += """
        <table>
        <thead>
            <tr>
                <th>服务器</th>
                <th>地址</th>
                <th>端口</th>
                <th>状态</th>
            </tr>
        </thead>
        <tbody>
        """
        for s in servers:
            status = "🟢 Online" if s.get("online") else "🔴 Offline"
            status_class = "success" if s.get("online") else "danger"
            html += f"""
            <tr>
                <td><strong>{s.get('server_id', 'Unknown')}</strong></td>
                <td>{s.get('host', '-')}</td>
                <td>{s.get('port', '-')}</td>
                <td><span class="badge {status_class}">{status}</span></td>
            </tr>
            """
        html += "</tbody></table>"
    
    return html


def page_jobs():
    """Jobs page"""
    jobs = get_jobs()
    
    html = """
    <h2>📋 任务监控</h2>
    <p>监控后台任务执行状态</p>
    """
    
    if not jobs:
        html += "<p>暂无运行中的任务</p>"
    else:
        html += """
        <table>
        <thead>
            <tr>
                <th>任务 ID</th>
                <th>描述</th>
                <th>状态</th>
                <th>目录</th>
                <th>运行时长</th>
            </tr>
        </thead>
        <tbody>
        """
        for j in jobs:
            status = j.get("status", "unknown")
            status_map = {
                "running": ("🔄 Running", "info"),
                "done": ("✅ Done", "success"),
                "failed": ("❌ Failed", "danger"),
                "pending": ("⏳ Pending", "warning")
            }
            status_text, status_class = status_map.get(status, (status, "info"))
            
            html += f"""
            <tr>
                <td><code>{j.get('job_id', '-')}</code></td>
                <td>{j.get('description', '-')[:40]}</td>
                <td><span class="badge {status_class}">{status_text}</span></td>
                <td><code>{j.get('workdir', '-')[:30]}</code></td>
                <td>{j.get('elapsed', '-')}</td>
            </tr>
            """
        html += "</tbody></table>"
    
    return html


def page_chat():
    """Chat page"""
    history = get_chat_history()
    
    # Simple chat UI using gr.Chatbot
    with gr.Column():
        gr.Markdown("## 💬 与 OmicsClaw 对话")
        gr.Markdown("*此功能需要 Discord Bot 在线*")
        
        chatbot = gr.Chatbot(
            label="对话历史",
            height=400
        )
        
        msg_input = gr.Textbox(
            label="发送消息",
            placeholder="输入你的问题...",
            lines=2
        )
        
        send_btn = gr.Button("发送", variant="primary")
        
        def respond(message, history):
            if not message:
                return "", history
            
            # Add user message
            history.append((message, None))
            
            # Get response
            response = send_chat_message(message)
            
            # Add bot response
            history[-1] = (message, response)
            
            return "", history
        
        send_btn.click(respond, [msg_input, chatbot], [msg_input, chatbot])
        msg_input.submit(respond, [msg_input, chatbot], [msg_input, chatbot])
    
    return gr.render()


def page_config():
    """Config page"""
    html = """
    <h2>⚙️ 配置</h2>
    <p>Bot 运行配置</p>
    
    <div style="background: var(--bg-secondary); padding: 20px; border-radius: 8px;">
        <h3>当前配置</h3>
        <ul>
            <li><strong>API 端口:</strong> {api_port}</li>
            <li><strong>WebSocket 端口:</strong> {ws_port}</li>
            <li><strong>Dashboard 端口:</strong> {dash_port}</li>
            <li><strong>工作目录:</strong> data/</li>
        </ul>
    </div>
    
    <h3>快速命令</h3>
    <pre style="background: var(--bg-secondary); padding: 15px; border-radius: 8px;">
# 重启 Bot
bash restart.sh

# 查看日志
tail -f /tmp/omicsclaw_bot.log

# 测试连接
/server test sjs
    </pre>
    """.format(api_port=API_PORT, ws_port=WS_PORT, dash_port=DASHBOARD_PORT)
    
    return html


# =====================
# Main App
# =====================

def create_app():
    """Create Gradio app"""
    
    with gr.Blocks(css=CSS, title="OmicsClaw Dashboard") as app:
        # Header
        gr.HTML("""
        <div id="header">
            <div id="title">🧬 OmicsClaw Dashboard</div>
            <div style="display: flex; gap: 10px;">
                <button class="gr-button" onclick="location.reload()">🔄 刷新</button>
            </div>
        </div>
        """)
        
        # Status bar
        gr.HTML(render_status_bar)
        
        # Auto-refresh status bar every 10 seconds
        gr.HTML("""
        <script>
        setInterval(() => {
            location.reload();
        }, 30000);
        </script>
        """)
        
        with gr.Row():
            # Sidebar
            with gr.Column(scale=1, min_width=200):
                gr.HTML("""
                <div id="sidebar">
                    <div class="menu-item active" onclick="showPage('jobs')">
                        <span class="menu-icon">📋</span>
                        <span>任务</span>
                    </div>
                    <div class="menu-item" onclick="showPage('servers')">
                        <span class="menu-icon">🖥️</span>
                        <span>服务器</span>
                    </div>
                    <div class="menu-item" onclick="showPage('chat')">
                        <span class="menu-icon">💬</span>
                        <span>对话</span>
                    </div>
                    <div class="menu-item" onclick="showPage('config')">
                        <span class="menu-icon">⚙️</span>
                        <span>配置</span>
                    </div>
                </div>
                <script>
                function showPage(page) {
                    // Simple page switching
                    document.querySelectorAll('.page-content').forEach(el => el.style.display = 'none');
                    document.getElementById('page-' + page).style.display = 'block';
                    
                    // Update active menu
                    document.querySelectorAll('.menu-item').forEach(el => el.classList.remove('active'));
                    event.currentTarget.classList.add('active');
                }
                </script>
                """)
            
            # Main content
            with gr.Column(scale=4):
                gr.HTML('<div class="page-content" id="page-jobs">')
                gr.Markdown("## 📋 任务监控")
                gr.Markdown("*实时监控后台任务执行状态*")
                jobs = get_jobs()
                if jobs:
                    jobs_html = "<table><thead><tr><th>ID</th><th>描述</th><th>状态</th><th>目录</th><th>运行时长</th></tr></thead><tbody>"
                    for j in jobs:
                        status = j.get("status", "unknown")
                        status_map = {"running": "🔄", "done": "✅", "failed": "❌", "pending": "⏳"}
                        jobs_html += f"<tr><td><code>{j.get('job_id', '-')}</code></td><td>{j.get('description', '-')[:30]}</td><td>{status_map.get(status, status)}</td><td><code>{j.get('workdir', '-')[:25]}</code></td><td>{j.get('elapsed', '-')}</td></tr>"
                    jobs_html += "</tbody></table>"
                    gr.HTML(jobs_html)
                else:
                    gr.Markdown("暂无运行中的任务")
                gr.HTML('</div>')
                
                gr.HTML('<div class="page-content" id="page-servers" style="display:none;">')
                gr.Markdown("## 🖥️ 服务器")
                servers = get_servers()
                if servers:
                    servers_html = "<table><thead><tr><th>服务器</th><th>地址</th><th>端口</th><th>状态</th></tr></thead><tbody>"
                    for s in servers:
                        status = "🟢 Online" if s.get("online") else "🔴 Offline"
                        servers_html += f"<tr><td><strong>{s.get('server_id', 'Unknown')}</strong></td><td>{s.get('host', '-')}</td><td>{s.get('port', '-')}</td><td>{status}</td></tr>"
                    servers_html += "</tbody></table>"
                    gr.HTML(servers_html)
                else:
                    gr.Markdown("暂无服务器配置")
                gr.HTML('</div>')
                
                gr.HTML('<div class="page-content" id="page-chat" style="display:none;">')
                gr.Markdown("## 💬 对话")
                gr.Markdown("*与 OmicsClaw 对话（需要 Bot 在线）*")
                gr.HTML('</div>')
                
                gr.HTML('<div class="page-content" id="page-config" style="display:none;">')
                gr.Markdown("## ⚙️ 配置")
                gr.Markdown(f"""
                - **API 端口**: {API_PORT}
                - **WebSocket 端口**: {WS_PORT}
                - **Dashboard 端口**: {DASHBOARD_PORT}
                """)
                gr.HTML('</div>')
    
    return app


def start_api_server(ssh_manager, agent):
    """Start FastAPI server in background thread"""
    from dashboard.api import init_api, app as fastapi_app
    import uvicorn
    
    init_api(ssh_manager, agent)
    
    def run():
        uvicorn.run(fastapi_app, host="127.0.0.1", port=API_PORT, log_level="warning")
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info(f"API server started on port {API_PORT}")


def start_websocket_server():
    """Start WebSocket server in background thread"""
    from dashboard.websocket_server import start_websocket_server
    
    def run():
        asyncio.run(start_websocket_server())
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info(f"WebSocket server started on port {WS_PORT}")


def main():
    """Main entry point"""
    logger.info("Starting OmicsClaw Dashboard...")
    
    # Check if API is running
    try:
        resp = requests.get(f"{API_BASE}/", timeout=2)
        logger.info("API already running")
    except:
        logger.warning("API not running - start bot first with dashboard enabled")
        print("⚠️  请先启动 OmicsClaw Bot，再运行 Dashboard")
        print(f"   或者在 bot.py 中集成 Dashboard")
        return
    
    # Create and launch app
    app = create_app()
    
    logger.info(f"Dashboard running at http://127.0.0.1:{DASHBOARD_PORT}")
    app.launch(server_name="127.0.0.1", server_port=DASHBOARD_PORT, show_error=True)


if __name__ == "__main__":
    main()
