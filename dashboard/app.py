#!/usr/bin/env python3
"""
OmicsClaw Dashboard - Dark Theme
A Gradio-based dashboard for monitoring and controlling OmicsClaw
"""

import requests
import time
import gradio as gr

# Configuration
API_PORT = 19766

# =====================
# Helper Functions
# =====================

def api_get(endpoint):
    try:
        resp = requests.get(f"http://127.0.0.1:{API_PORT}{endpoint}", timeout=5)
        return resp.json()
    except:
        return {}

def api_post(endpoint, data):
    try:
        resp = requests.post(f"http://127.0.0.1:{API_PORT}{endpoint}", json=data, timeout=30)
        return resp.json()
    except:
        return {}

def get_stats():
    return api_get("/stats")

def get_servers():
    result = api_get("/servers")
    if isinstance(result, list):
        return result
    return []

def get_jobs():
    result = api_get("/jobs")
    if isinstance(result, list):
        return result
    return []

# =====================
# Page Builders
# =====================

def build_jobs_page():
    with gr.Column():
        gr.Markdown("## 📋 任务监控", elem_classes=["page-title"])
        jobs = get_jobs()
        
        if not jobs:
            gr.Markdown("暂无运行中的任务", elem_classes=["empty-state"])
        else:
            for j in jobs:
                status = j.get("status", "unknown")
                status_map = {
                    "running": ("🔄 Running", "info"),
                    "done": ("✅ 完成", "success"), 
                    "failed": ("❌ 失败", "danger"),
                    "pending": ("⏳ 等待", "warning")
                }
                status_text, status_class = status_map.get(status, (status, "info"))
                
                with gr.Card():
                    gr.Markdown(f"**{j.get('job_id', '-')}** — {j.get('description', '')[:50]}")
                    gr.Markdown(f"状态: `{status_text}` | 目录: `{j.get('workdir', '')}` | 耗时: {j.get('elapsed', '-')}")

def build_servers_page():
    with gr.Column():
        gr.Markdown("## 🖥️ 服务器", elem_classes=["page-title"])
        servers = get_servers()
        
        if not servers:
            gr.Markdown("暂无服务器配置", elem_classes=["empty-state"])
        else:
            for s in servers:
                status = "🟢 Online" if s.get("online") else "🔴 Offline"
                with gr.Card():
                    gr.Markdown(f"**{s.get('server_id', 'Unknown')}** ({status})")
                    gr.Markdown(f"地址: `{s.get('host', '-')}:{s.get('port', '-')}`")

def build_chat_page():
    with gr.Column():
        gr.Markdown("## 💬 对话", elem_classes=["page-title"])
        gr.Markdown("*此功能需要 Discord Bot 在线*")
        
        def respond(message, history):
            if not message:
                return "", history
            history.append((message, "处理中..."))
            result = api_post("/chat", {"message": message, "user_id": "dashboard"})
            response = result.get("text", "⚠️ 请求失败")
            history[-1] = (message, response)
            return "", history
        
        chatbot = gr.Chatbot(label="对话历史", height=400)
        msg_input = gr.Textbox(label="发送消息", placeholder="输入你的问题...")
        send_btn = gr.Button("发送", variant="primary")
        
        send_btn.click(respond, [msg_input, chatbot], [msg_input, chatbot])
        msg_input.submit(respond, [msg_input, chatbot], [msg_input, chatbot])

def build_config_page():
    with gr.Column():
        gr.Markdown("## ⚙️ 配置", elem_classes=["page-title"])
        gr.Markdown("### 当前配置", elem_classes=["section-title"])
        gr.Markdown(f"""
        - **API 端口**: {API_PORT}
        - **Dashboard 端口**: 7860
        - **工作目录**: data/
        """)
        
        gr.Markdown("### 快速命令", elem_classes=["section-title"])
        gr.Markdown("""
        ```bash
        # 重启 Bot
        bash restart.sh
        
        # 查看日志
        tail -f /tmp/omicsclaw_bot.log
        ```
        """)

# =====================
# Main App
# =====================

CSS = """
/* Dark Theme */
:root {
    --bg-primary: #0D0D0D;
    --bg-secondary: #1A1A1A;
    --bg-card: #1E1E1E;
    --text-primary: #FFFFFF;
    --text-secondary: #A0A0A0;
    --accent-blue: #3B82F6;
    --accent-light: #1E3A5F;
    --border: #333333;
}
body { background: var(--bg-primary); color: var(--text-primary); }
.gradio-container { background: var(--bg-primary) !important; }
.page-title { color: var(--accent-blue) !important; margin-bottom: 20px !important; }
.empty-state { color: var(--text-secondary) !important; }
.section-title { color: var(--text-secondary) !important; margin-top: 20px !important; }
.card { background: var(--bg-card) !important; border: 1px solid var(--border) !important; }
"""

with gr.Blocks(css=CSS, title="OmicsClaw Dashboard") as app:
    gr.Markdown("# 🧬 OmicsClaw Dashboard", elem_id="title")
    
    # Status bar
    stats = get_stats()
    gr.Markdown(f"""
    ---
    **状态**: {stats.get('servers_online',0)}/{stats.get('servers',0)} 服务器在线 | {stats.get('jobs_running',0)}/{stats.get('jobs',0)} 任务运行
    ---""", elem_id="status")
    
    with gr.Row():
        with gr.Column(scale=1, min_width=150):
            gr.Markdown("### 导航")
            jobs_btn = gr.Button("📋 任务", variant="secondary")
            servers_btn = gr.Button("🖥️ 服务器", variant="secondary")
            chat_btn = gr.Button("💬 对话", variant="secondary")
            config_btn = gr.Button("⚙️ 配置", variant="secondary")
        
        with gr.Column(scale=4):
            jobs_page = gr.Column(visible=True)
            servers_page = gr.Column(visible=False)
            chat_page = gr.Column(visible=False)
            config_page = gr.Column(visible=False)
            
            with jobs_page:
                build_jobs_page()
            with servers_page:
                build_servers_page()
            with chat_page:
                build_chat_page()
            with config_page:
                build_config_page()
    
    # Navigation handlers
    def show_page(page):
        return {
            jobs_page: page == "jobs",
            servers_page: page == "servers", 
            chat_page: page == "chat",
            config_page: page == "config"
        }
    
    jobs_btn.click(lambda: show_page("jobs"), None, [jobs_page, servers_page, chat_page, config_page])
    servers_btn.click(lambda: show_page("servers"), None, [jobs_page, servers_page, chat_page, config_page])
    chat_btn.click(lambda: show_page("chat"), None, [jobs_page, servers_page, chat_page, config_page])
    config_btn.click(lambda: show_page("config"), None, [jobs_page, servers_page, chat_page, config_page])

# =====================
# Launcher
# =====================

def main():
    print("=" * 50)
    print("🧬 OmicsClaw Dashboard")
    print("=" * 50)
    print(f"\n🚀 Dashboard running at http://127.0.0.1:7860")
    print("   Press Ctrl+C to stop\n")
    app.launch(server_name="127.0.0.1", server_port=7860)

if __name__ == "__main__":
    main()
