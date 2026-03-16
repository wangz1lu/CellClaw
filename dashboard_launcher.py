#!/usr/bin/env python3
"""
Standalone Dashboard launcher
Usage: python dashboard_launcher.py
"""

import sys
import os
import requests
import time

API_PORT = 19766
DASHBOARD_PORT = 7860


def wait_for_api(timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"http://127.0.0.1:{API_PORT}/", timeout=2)
            if resp.status_code == 200:
                return True
        except:
            pass
        time.sleep(1)
    return False


def main():
    print("=" * 50)
    print("🧬 OmicsClaw Dashboard Launcher")
    print("=" * 50)
    
    print(f"\n📡 Checking API server...")
    if not wait_for_api():
        print(f"❌ API not responding on port {API_PORT}")
        print("   Please start OmicsClaw Bot first:")
        print("   cd OmicsClaw && python bot.py")
        return
    
    print(f"✅ API server is running")
    print(f"\n🚀 Starting Dashboard on http://127.0.0.1:{DASHBOARD_PORT}")
    print("   Press Ctrl+C to stop\n")
    
    from dashboard.app import main as gradio_main
    gradio_main()


if __name__ == "__main__":
    main()
