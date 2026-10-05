###################
# Created : 2026-10-03 GB
# Purpose : Handles persistent idiot connections to the D.I.P.S.H.I.T. moderator.
# Notes   : Connection lifecycle is separate from runtime entity storage.
###################

from fastapi import WebSocket, WebSocketDisconnect

from idiots._idiots import IdiotAlreadyConnectedError, IdiotRegistry
from idiots.idiot import Idiot, Personality, RoomEvent


class IdiotConnections:
    @staticmethod
    def _key(name):
        return name.casefold()

    def __init__(self):
        self._websockets = {}

    def add(self, idiot: Idiot, websocket: WebSocket):
        self._websockets[self._key(idiot.name)] = websocket

    def remove(self, idiot: Idiot):
        self._websockets.pop(self._key(idiot.name), None)

    async def send_prompt(self, idiot: Idiot, prompt: str):
        websocket = self._websockets.get(self._key(idiot.name))

        if websocket is None:
            raise ValueError(f'Idiot "{idiot.name}" is not connected.')

        await websocket.send_json(
            {
                "prompt": prompt,
                "type": "prompt"
            }
        )


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


async def _receive_idiot_message(idiot: Idiot, payload, room):
    if not isinstance(payload, dict):
        return

    message_type = payload.get("type")

    if message_type == "state":
        state = payload.get("state")

        if state in {"IDLE", "SPEAKING", "THINKING"}:
            idiot.state = state

    elif message_type == "trace":
        content = payload.get("content")

        if isinstance(content, str):
            idiot.trace += content

    elif message_type == "speech_start":
        speech_id = payload.get("speech_id")

        if isinstance(speech_id, str) and speech_id:
            room.append(
                RoomEvent(
                    source=idiot.name,
                    event_id=speech_id,
                    event_type="speech",
                    complete=False
                )
            )

    elif message_type == "speech_chunk":
        speech_id = payload.get("speech_id")
        content = payload.get("content")

        if isinstance(speech_id, str) and isinstance(content, str):
            speech = next(
                (
                    item
                    for item in reversed(room)
                    if item.event_id == speech_id
                    and item.source == idiot.name
                ),
                None
            )

            if speech is not None and not speech.complete:
                speech.content += content

    elif message_type == "speech_end":
        speech_id = payload.get("speech_id")
        speech = next(
            (
                item
                for item in reversed(room)
                if item.event_id == speech_id
                and item.source == idiot.name
            ),
            None
        )

        if speech is not None:
            speech.complete = True


async def _reject_connection(websocket, error):
    await websocket.send_json(
        {
            "error": error,
            "type": "connection_rejected"
        }
    )
    await websocket.close(code=1008)


async def connect_idiot(
    websocket: WebSocket,
    registry: IdiotRegistry,
    connections: IdiotConnections,
    room: list[RoomEvent]
):
    await websocket.accept()

    idiot = None

    try:
        payload = await websocket.receive_json()
        idiot = _parse_connection(payload)
        registry.add(idiot)
        connections.add(idiot, websocket)

        await websocket.send_json(idiot.connected_payload())

        room.append(
            RoomEvent(
                source="MODERATOR",
                event_id=str(idiot.connection_id),
                event_type="presence",
                content=f"{idiot.name} has entered the room."
            )
        )

        while True:
            payload = await websocket.receive_json()
            await _receive_idiot_message(idiot, payload, room)

    except IdiotAlreadyConnectedError as error:
        await _reject_connection(websocket, str(error))

    except ValueError as error:
        await _reject_connection(websocket, str(error))

    except WebSocketDisconnect:
        pass

    finally:
        if idiot is not None:
            connections.remove(idiot)
            registry.remove(idiot)
