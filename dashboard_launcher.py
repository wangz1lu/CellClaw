#!/usr/bin/env python3
"""Dashboard launcher"""
import requests, time, sys

API_PORT = 19766

def wait_api():
    for _ in range(30):
        try:
            if requests.get(f"http://127.0.0.1:{API_PORT}/").status_code == 200:
                return True
        except: pass
        time.sleep(1)
    return False

if __name__ == "__main__":
    print("🧬 CellClaw Dashboard")
    if not wait_api():
        print(f"❌ API not running on {API_PORT}. Start bot first.")
        sys.exit(1)
    print(f"🚀 http://127.0.0.1:7860")
    
    from dashboard.app import app
    app.launch(server_name="127.0.0.1", server_port=7860)
