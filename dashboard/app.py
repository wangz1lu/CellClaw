#!/usr/bin/env python3
"""
OmicsClaw Dashboard - Simple Dark Theme
"""

import requests
import gradio as gr

API_PORT = 19766

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
    return result if isinstance(result, list) else []

def get_jobs():
    result = api_get("/jobs")
    return result if isinstance(result, list) else []

def respond(message, history):
    if not message:
        return "", history
    history.append((message, "处理中..."))
    result = api_post("/chat", {"message": message, "user_id": "dashboard"})
    response = result.get("text", "⚠️ 请求失败")
    history[-1] = (message, response)
    return "", history

# Dark theme CSS
CSS = """
:root { --bg: #0D0D0D; --card: #1E1E1E; --text: #FFF; --accent: #3B82F6; }
body, .gradio-container { background: var(--bg) !important; color: var(--text) !important; }
"""

with gr.Blocks(css=CSS, title="OmicsClaw") as app:
    gr.Markdown("# 🧬 OmicsClaw Dashboard")
    
    stats = get_stats()
    gr.Markdown(f"**状态**: {stats.get('servers_online',0)}/{stats.get('servers',0)} 服务器 | {stats.get('jobs_running',0)}/{stats.get('jobs',0)} 任务")
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 导航")
            jobs_btn = gr.Button("📋 任务")
            servers_btn = gr.Button("🖥️ 服务器")
            chat_btn = gr.Button("💬 对话")
            config_btn = gr.Button("⚙️ 配置")
        
        with gr.Column(scale=4):
            jobs_tab = gr.Tab("任务")
            with jobs_tab:
                jobs = get_jobs()
                if jobs:
                    for j in jobs:
                        status = j.get("status", "?")
                        status_icon = {"running": "🔄", "done": "✅", "failed": "❌", "pending": "⏳"}.get(status, "❓")
                        gr.Markdown(f"- **{j.get('job_id')}** {status_icon} {status} | {j.get('elapsed','')}")
                else:
                    gr.Markdown("暂无任务")
            
            servers_tab = gr.Tab("服务器")
            with servers_tab:
                servers = get_servers()
                if servers:
                    for s in servers:
                        status = "🟢" if s.get("online") else "🔴"
                        gr.Markdown(f"- **{s.get('server_id')}** {status} | {s.get('host')}:{s.get('port')}")
                else:
                    gr.Markdown("暂无服务器")
            
            chat_tab = gr.Tab("对话")
            with chat_tab:
                gr.Markdown("*此功能需要 Discord Bot 在线*")
                chatbot = gr.Chatbot(label="对话", height=300)
                msg = gr.Textbox(label="消息")
                btn = gr.Button("发送", variant="primary")
                btn.click(respond, [msg, chatbot], [msg, chatbot])
                msg.submit(respond, [msg, chatbot], [msg, chatbot])
            
            config_tab = gr.Tab("配置")
            with config_tab:
                gr.Markdown(f"""
                - API: {API_PORT}
                - Dashboard: 7860
                """)

if __name__ == "__main__":
    app.launch(server_name="127.0.0.1", server_port=7860)
