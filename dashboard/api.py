#!/usr/bin/env python3
"""
CellClaw REST API
Provides endpoints for server and job status
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger("omicsclaw.api")

# Global references (set by bot)
_ssh_manager = None
_agent = None


def init_api(ssh_manager, agent):
    """Initialize API with bot references"""
    global _ssh_manager, _agent
    _ssh_manager = ssh_manager
    _agent = agent


app = FastAPI(title="CellClaw API", version="1.0.0")


# Models
class ServerStatus(BaseModel):
    server_id: str
    name: str
    host: str
    port: int
    online: bool
    conda_envs: List[str] = []


class JobStatus(BaseModel):
    job_id: str
    description: str
    status: str
    workdir: str
    conda_env: Optional[str]
    started_at: str
    elapsed: str
    error_summary: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    user_id: str


class ChatResponse(BaseModel):
    text: str
    figures: List[str] = []


# Endpoints
@app.get("/")
async def root():
    return {"name": "CellClaw API", "version": "1.0.0"}


@app.get("/servers", response_model=List[ServerStatus])
async def get_servers():
    """Get all server statuses"""
    if not _ssh_manager:
        raise HTTPException(status_code=500, detail="API not initialized")
    
    try:
        servers = []
        registry = _ssh_manager._registry
        
        # Get all server configs
        for key, data in registry._servers.items():
            # Check if connected - connections are in _connections._pool
            # Show as online if server is configured (reachable)
            is_online = True
            
            servers.append(ServerStatus(
                server_id=data.get("server_id", key),
                name=data.get("server_id", "Unknown"),
                host=data.get("host", "-"),
                port=data.get("port", 22),
                online=is_online,
                conda_envs=[]
            ))
        
        return servers
    except Exception as e:
        logger.error(f"Error getting servers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs", response_model=List[JobStatus])
async def get_jobs(user_id: str = None):
    """Get all jobs or jobs for specific user"""
    if not _ssh_manager:
        raise HTTPException(status_code=500, detail="API not initialized")
    
    try:
        jobs = []
        
        for job_id, job in _ssh_manager._jobs.items():
            # Filter by user if specified
            if user_id and job.discord_user_id != user_id:
                continue
            
            jobs.append(JobStatus(
                job_id=job.job_id,
                description=job.command[:50] if job.command else "Unknown",
                status=job.status.value,
                workdir=job.workdir,
                conda_env=job.conda_env,
                started_at=job.started_at.isoformat(),
                elapsed=job.elapsed(),
                error_summary=job.error_summary
            ))
        
        # Sort by started_at descending
        jobs.sort(key=lambda x: x.started_at, reverse=True)
        
        return jobs
    except Exception as e:
        logger.error(f"Error getting jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}/log")
async def get_job_log(job_id: str, tail: int = 50):
    """Get job log"""
    if not _ssh_manager:
        raise HTTPException(status_code=500, detail="API not initialized")
    
    try:
        # This requires discord_user_id - for now return empty
        return {"job_id": job_id, "log": "Log access requires user context"}
    except Exception as e:
        logger.error(f"Error getting job log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Add session path config
import os
from pathlib import Path

DATA_DIR = os.environ.get("OMICSCLAW_DATA", str(Path(__file__).parent.parent / "data"))
SESSION_DIR = Path(DATA_DIR) / "sessions"

# Also fix the API to use absolute path
@app.get("/sessions/{user_id}/history")
async def get_session_history(user_id: str, limit: int = 50):
    """Get chat history for a user"""
    try:
        import json
        
        session_file = SESSION_DIR / f"{user_id}.jsonl"
        if not session_file.exists():
            return {"messages": []}
        
        messages = []
        with open(session_file) as f:
            for line in f:
                if line.strip():
                    msg = json.loads(line)
                    messages.append(msg)
                    if len(messages) >= limit:
                        break
        
        return {"messages": messages}
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        return {"messages": [], "error": str(e)}


@app.post("/sessions/{user_id}/message")
async def add_session_message(user_id: str):
    """Add a message to the session file"""
    try:
        import json
        from datetime import datetime
        
        session_file = SESSION_DIR / f"{user_id}.jsonl"
        session_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Read request body
        content = await request.json()
        msg = {
            "role": content.get("role", "user"),
            "content": content.get("content", ""),
            "timestamp": datetime.now().isoformat()
        }
        
        with open(session_file, "a") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        
        return {"success": True, "message": msg}
    except Exception as e:
        logger.error(f"Error adding message: {e}")
        return {"success": False, "error": str(e)}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a chat message (for dashboard)"""
    if not _agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        # Process message through agent
        response = await _agent.handle_message(
            message=request.message,
            discord_user_id=request.user_id,
            channel_id=f"dashboard-{request.user_id}",
            is_dm=True
        )
        
        return ChatResponse(
            text=response.text or "",
            figures=response.figures or []
        )
    except Exception as e:
        logger.error(f"Error in chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/skills")
async def get_skills():
    """Get all available skills"""
    import os
    from pathlib import Path
    
    import os
    # Use absolute path based on project root
    project_root = os.environ.get('CELLCLAW_ROOT', '/Users/wzlmac/.openclaw/workspace-developer/bioinfo_analysis/CellClaw')
    skills_dir = Path(project_root) / "skills"
    skills = []
    
    if skills_dir.exists():
        for skill_path in skills_dir.iterdir():
            if skill_path.is_dir() and (skill_path / "SKILL.md").exists():
                skill_info = {
                    "id": skill_path.name,
                    "name": skill_path.name,
                    "description": "",
                    "triggers": [],
                    "languages": []
                }
                
                # Read SKILL.md
                skill_md = (skill_path / "SKILL.md").read_text()
                lines = skill_md.split('\n')
                in_header = False
                for line in lines:
                    if line.startswith('---'):
                        in_header = not in_header
                        continue
                    if in_header:
                        if line.startswith('name:'):
                            skill_info['name'] = line.split(':', 1)[1].strip()
                        elif line.startswith('triggers:'):
                            # Parse triggers
                            triggers = []
                            for l in lines[lines.index(line):]:
                                if l.strip().startswith('- '):
                                    triggers.append(l.strip()[2:])
                                elif l.strip() and not l.strip().startswith('- '):
                                    break
                            skill_info['triggers'] = triggers
                        elif line.startswith('languages:'):
                            langs = []
                            for l in lines[lines.index(line):]:
                                if l.strip().startswith('- '):
                                    langs.append(l.strip()[2:])
                                elif l.strip() and not l.strip().startswith('- '):
                                    break
                            skill_info['languages'] = langs
                
                skills.append(skill_info)
    
    return skills


@app.get("/stats")
async def get_stats():
    """Get overall statistics"""
    if not _ssh_manager:
        return {"servers": 0, "jobs": 0, "connected": 0}
    
    total_servers = len(_ssh_manager._registry._servers)
    
    # Count connected servers
    connected = 0
    try:
        connected = len(_ssh_manager._connections._pool)
    except:
        pass
    
    total_jobs = len(_ssh_manager._jobs)
    running_jobs = sum(1 for j in _ssh_manager._jobs.values() if j.status.value == "running")
    
    return {
        "servers": total_servers,
        "servers_online": connected,
        "jobs": total_jobs,
        "jobs_running": running_jobs
    }


if __name__ == "__main__":
    import uvicorn
    # WebSocket endpoint for real-time updates

@app.get("/api/ws/status")
async def ws_status():
    """Get WebSocket connection status"""
    from agents.websocket_manager import get_websocket_manager
    ws_manager = get_websocket_manager()
    return {
        "connected": True,
        "active_connections": len(ws_manager.connections._connections),
        "tasks_tracked": len(ws_manager._tasks)
    }

    @app.websocket("/ws/{user_id}")
    async def websocket_endpoint(websocket: WebSocket, user_id: str):
        await websocket.accept()
        
        # Get WebSocket manager
        from agents.websocket_manager import get_websocket_manager
        ws_manager = get_websocket_manager()
        
        # Register connection
        await ws_manager.handle_connect(websocket, user_id=user_id)
        
        try:
            while True:
                data = await websocket.receive_text()
                await ws_manager.handle_message(websocket, data)
        except WebSocketDisconnect:
            await ws_manager.handle_disconnect(websocket)
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            await ws_manager.handle_disconnect(websocket)

    uvicorn.run(app, host="127.0.0.1", port=19766)


# Serve dashboard static files
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    
@app.get("/dashboard")
async def dashboard():
    """Serve dashboard"""
    dashboard_path = os.path.join(static_dir, "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    return {"error": "Dashboard not found"}
