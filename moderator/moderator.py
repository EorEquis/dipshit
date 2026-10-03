###################
# Created : 2026-10-03 GB
# Purpose : Main entry point for the D.I.P.S.H.I.T. moderator service.
# Notes   : Provides the persistent idiot connection endpoint and live registry.
###################

from fastapi import FastAPI, WebSocket

from idiots._idiots import IdiotRegistry
from operations.connections import connect_idiot


app = FastAPI(title="D.I.P.S.H.I.T. Moderator")
registry = IdiotRegistry()


@app.get("/api/idiots")
async def get_idiots():
    return {
        "idiots": registry.snapshot()
    }


@app.websocket("/ws/idiot")
async def idiot_connection(websocket: WebSocket):
    await connect_idiot(websocket, registry)
