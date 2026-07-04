# Copyright 2026 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     https://www.apache.org/licenses/LICENSE-2.0

import os
import uuid
import json
import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from app.agent import app as adk_app
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web_server")

app = FastAPI(
    title="Public Health Awareness Agent Dashboard",
    description="Full-stack interface demonstrating Google ADK multi-agent reasoning flow."
)

# Enable CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Session Service - InMemory to guarantee no permanent health data storage
session_service = InMemorySessionService()

# API Endpoint to start or stream chat
@app.get("/api/chat")
async def chat_stream(query: str, session_id: str = None):
    """Streams execution events of the multi-agent system back to the client using SSE."""
    if not session_id:
        session_id = f"session_{uuid.uuid4().hex[:10]}"
        
    async def event_generator():
        runner = Runner(
            app=adk_app,
            session_service=session_service
        )
        
        # Ensure session is created
        try:
            await session_service.create_session(app_name="app", user_id="web_user", session_id=session_id)
        except Exception:
            # Already exists
            pass
            
        new_msg = types.Content(role="user", parts=[types.Part.from_text(text=query)])
        
        try:
            # Stream the events from ADK
            async for event in runner.run_async(
                user_id="web_user",
                session_id=session_id,
                new_message=new_msg,
                yield_user_message=True
            ):
                event_dict = event.model_dump(mode="json")
                yield {
                    "event": "agent_event",
                    "data": json.dumps({
                        "author": event_dict.get("author") or "system",
                        "event_id": event_dict.get("id"),
                        "content": event_dict.get("content"),
                        "output": event_dict.get("output"),
                        "actions": event_dict.get("actions"),
                        "timestamp": event_dict.get("timestamp")
                    })
                }
        except Exception as e:
            logger.exception("Error during agent execution")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }
            
    return EventSourceResponse(event_generator())

# Expose session information for safety check
@app.get("/api/session/clear")
async def clear_session(session_id: str):
    """Explicitly deletes session in-memory to prevent data retention."""
    try:
        await session_service.delete_session(app_name="app", user_id="web_user", session_id=session_id)
        return {"status": "success", "message": f"Session {session_id} successfully cleared."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Serve Static Frontend Files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)

@app.get("/")
async def get_index():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h3>Web dashboard static files are being prepared... Please reload in a moment.</h3>")

# Mount static directory for JS and CSS files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.web_server:app", host="0.0.0.0", port=8000, reload=True)
