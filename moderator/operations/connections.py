###################
# Created : 2026-10-03 GB
# Purpose : Handles persistent idiot connections to the D.I.P.S.H.I.T. moderator.
# Notes   : Connection lifecycle is separate from runtime entity storage.
###################

from fastapi import WebSocket, WebSocketDisconnect

from entities.idiot import Idiot, Personality
from operations.registry import IdiotAlreadyConnectedError, IdiotRegistry


async def connect_idiot(websocket: WebSocket, registry: IdiotRegistry):
    await websocket.accept()

    idiot = None

    try:
        payload = await websocket.receive_json()
        idiot = _parse_connection(payload)
        registry.add(idiot)

        await websocket.send_json(idiot.connected_payload())

        while True:
            await websocket.receive()

    except IdiotAlreadyConnectedError as error:
        await _reject_connection(websocket, str(error))

    except ValueError as error:
        await _reject_connection(websocket, str(error))

    except WebSocketDisconnect:
        pass

    finally:
        if idiot is not None:
            registry.remove(idiot)


def _parse_connection(payload):
    if not isinstance(payload, dict):
        raise ValueError("Connection payload must be a JSON object.")

    if set(payload) != {"name", "personality", "type"}:
        raise ValueError(
            'Connection payload must contain exactly "type", "name", and "personality".'
        )

    if payload["type"] != "connect":
        raise ValueError('First message must have type "connect".')

    name = payload["name"]
    personality = payload["personality"]

    if not isinstance(name, str) or not name.strip():
        raise ValueError("Idiot name must be a non-empty string.")

    return Idiot(
        name=name.strip(),
        personality=_parse_personality(personality)
    )


def _parse_personality(payload):
    fields = {"curiosity", "friendliness", "sociability"}

    if not isinstance(payload, dict) or set(payload) != fields:
        raise ValueError(
            'Personality must contain exactly "curiosity", "friendliness", and "sociability".'
        )

    for field in sorted(fields):
        value = payload[field]

        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f'Personality "{field}" must be an integer from 1 to 100.')

        if value < 1 or value > 100:
            raise ValueError(f'Personality "{field}" must be an integer from 1 to 100.')

    return Personality(
        curiosity=payload["curiosity"],
        friendliness=payload["friendliness"],
        sociability=payload["sociability"]
    )


async def _reject_connection(websocket, error):
    await websocket.send_json(
        {
            "error": error,
            "type": "connection_rejected"
        }
    )
    await websocket.close(code=1008)
