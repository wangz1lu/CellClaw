#!/usr/bin/env python3
"""Start just the API server"""
import sys, os, asyncio, logging, threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("omicsclaw.api.start")

def start_api(ssh_manager, agent):
    from dashboard.api import init_api, app as fastapi_app
    import uvicorn
    init_api(ssh_manager, agent)
    def run():
        uvicorn.run(fastapi_app, host="127.0.0.1", port=19766, log_level="warning")
    threading.Thread(target=run, daemon=True).start()
    logger.info("API server started on port 19766")

def start_ws():
    from dashboard.websocket_server import start_websocket_server
    def run():
        asyncio.run(start_websocket_server())
    threading.Thread(target=run, daemon=True).start()
    logger.info("WebSocket server started on port 19765")

if __name__ == "__main__":
    print("Run from bot.py")
