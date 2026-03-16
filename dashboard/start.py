#!/usr/bin/env python3
"""
Start just the API server (for integration with bot)
This doesn't require gradio
"""

import sys
import os
import asyncio
import logging
import threading

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("omicsclaw.api.start")


def start_api(ssh_manager, agent):
    """Start API server in background thread"""
    from dashboard.api import init_api, app as fastapi_app
    import uvicorn
    
    init_api(ssh_manager, agent)
    
    def run():
        uvicorn.run(fastapi_app, host="127.0.0.1", port=8766, log_level="warning")
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info(f"API server started on port 8766")


def start_ws():
    """Start WebSocket server in background thread"""
    from dashboard.websocket_server import start_websocket_server
    
    def run():
        asyncio.run(start_websocket_server())
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info(f"WebSocket server started on port 8765")


if __name__ == "__main__":
    print("Run from bot.py instead:")
    print("from dashboard.start import start_api, start_ws")
    print("start_api(ssh_manager, agent)")
