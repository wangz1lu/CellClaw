#!/usr/bin/env python3
"""
OmicsClaw WebSocket Server
Provides real-time communication with Dashboard
"""

import asyncio
import json
import logging
from typing import Dict, Set, Callable, Any
from datetime import datetime

logger = logging.getLogger("omicsclaw.websocket")

# Global state
connected_clients: Set[Any] = set()
message_callback: Callable = None


def set_message_callback(callback: Callable):
    """Set callback for incoming messages from dashboard"""
    global message_callback
    message_callback = callback


async def broadcast(event: str, data: dict):
    """Broadcast event to all connected clients"""
    if not connected_clients:
        return
    
    message = json.dumps({"event": event, "data": data, "timestamp": datetime.now().isoformat()})
    
    # Create list to avoid modification during iteration
    clients = list(connected_clients)
    
    for client in clients:
        try:
            await client.send(message)
        except Exception as e:
            logger.warning(f"Failed to send to client: {e}")
            connected_clients.discard(client)


async def handle_client(websocket, path):
    """Handle WebSocket client connection"""
    connected_clients.add(websocket)
    logger.info(f"Client connected. Total: {len(connected_clients)}")
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                event = data.get("event")
                payload = data.get("data", {})
                
                # Handle different events
                if event == "chat_message":
                    # Forward to bot for processing
                    if message_callback:
                        result = await message_callback(payload)
                        # Send response back
                        await websocket.send(json.dumps({
                            "event": "chat_response",
                            "data": result
                        }))
                elif event == "ping":
                    await websocket.send(json.dumps({"event": "pong"}))
                    
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON: {message}")
            except Exception as e:
                logger.error(f"Error handling message: {e}")
                
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        connected_clients.discard(websocket)
        logger.info(f"Client disconnected. Total: {len(connected_clients)}")


async def start_websocket_server(host: str = "127.0.0.1", port: int = 18765):
    """Start WebSocket server"""
    import websockets
    
    logger.info(f"Starting WebSocket server on {host}:{port}")
    
    async with websockets.serve(handle_client, host, port):
        logger.info(f"WebSocket server running on ws://{host}:{port}")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(start_websocket_server())
