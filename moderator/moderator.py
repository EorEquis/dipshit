###################
# Created : 2026-10-03 GB
# Purpose : Main entry point for the D.I.P.S.H.I.T. moderator service.
# Notes   : Provides persistent idiot connections, live status, and manual test prompts.
###################

from fastapi import FastAPI, HTTPException, WebSocket

from idiots._idiots import IdiotRegistry
from operations.connections import IdiotConnections, connect_idiot


app = FastAPI(title="D.I.P.S.H.I.T. Moderator")
connections = IdiotConnections()
registry = IdiotRegistry()
room = []


@app.get("/api/idiots")
async def get_idiots():
    return {
        "idiots": registry.snapshot()
    }


@app.get("/api/room")
async def get_room():
    return {
        "events": [
            {
                "complete": event.complete,
                "content": event.content,
                "event_id": event.event_id,
                "event_type": event.event_type,
                "source": event.source,
                "started_at": event.started_at.isoformat()
            }
            for event in room
        ]
    }


@app.post("/api/idiots/{name}/prompt")
async def prompt_idiot(name: str, payload: dict):
    idiot = registry.get(name)

    if idiot is None:
        raise HTTPException(status_code=404, detail=f'Idiot "{name}" is not connected.')

    if idiot.state != "IDLE":
        raise HTTPException(status_code=409, detail=f'Idiot "{idiot.name}" is {idiot.state}.')

    prompt = payload.get("prompt")

    if not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt must be a non-empty string.")

    idiot.state = "THINKING"
    await connections.send_prompt(idiot, prompt.strip())

    return {
        "name": idiot.name,
        "prompt": prompt.strip(),
        "type": "prompt_sent"
    }


@app.websocket("/ws/idiot")
async def idiot_connection(websocket: WebSocket):
    await connect_idiot(websocket, registry, connections, room)
