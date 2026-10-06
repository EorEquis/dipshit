###################
# Created : 2026-10-03 GB
# Purpose : Handles persistent idiot connections to the D.I.P.S.H.I.T. moderator.
# Notes   : Connection lifecycle is separate from runtime entity storage.
###################

import json

from fastapi import WebSocket, WebSocketDisconnect

from idiots._idiots import IdiotAlreadyConnectedError, IdiotRegistry
from idiots.idiot import Idiot, Personality, RoomEvent


INITIAL_PROMPT = """You are <botname>. You are in a room with other people. You receive messages. Decide if you wish to respond to each message. Your messages should be more engaging than simply repeating what you received. Your response may contain multiple messages. Make each message a single line beginning with "To: everyone" or "To: <name>" to indicate who should receive your message. Replace <name> with the name of the person you are addressing. Provide only your messages; you do not need to include an explanation or rationale. system messages are general information about the room. Do not ever address a message to the moderator. You may initiate your own messages. In any turn, you may respond to the messages in the payload you receive or initiate a new message. If you do not wish to respond to a message, say exactly "N_S" on a line by itself. """


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

    async def send_message(self, idiot: Idiot, message: dict):
        idiot.message_queue.append(message)

        if idiot.state == "IDLE":
            await self.send_queued_messages(idiot)

    async def send_queued_messages(self, idiot: Idiot):
        if idiot.state != "IDLE" or not idiot.message_queue:
            return

        messages = idiot.message_queue
        idiot.message_queue = []

        prompt = json.dumps(
            {"messages": [{"message": message} for message in messages]},
            separators=(",", ":")
        )

        if not idiot.has_received_message:
            prompt = (
                INITIAL_PROMPT.replace("<botname>", idiot.name)
                + "\n\n"
                + prompt
            )
            idiot.has_received_message = True

        idiot.state = "THINKING"

        try:
            await self.send_prompt(idiot, prompt)
        except Exception:
            idiot.message_queue = messages + idiot.message_queue
            idiot.state = "IDLE"
            raise

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


async def _receive_idiot_message(
    idiot: Idiot,
    payload,
    registry: IdiotRegistry,
    connections: IdiotConnections,
    room
):
    if not isinstance(payload, dict):
        return

    message_type = payload.get("type")

    if message_type == "state":
        state = payload.get("state")

        if state in {"IDLE", "SPEAKING", "THINKING"}:
            idiot.state = state

            if state == "IDLE":
                await connections.send_queued_messages(idiot)

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

            if speech.content.strip() == "N_S":
                room.remove(speech)
                return

            if speech.content.lstrip().casefold().startswith("to: everyone"):
                for recipient in registry.idiots():
                    if recipient is idiot:
                        continue

                    await connections.send_message(
                        recipient,
                        {
                            "sent_from": idiot.name,
                            "message_type": "speech",
                            "is_private": "no",
                            "message_content": speech.content.strip(),
                            "message_age": "0 seconds"
                        }
                    )


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
        existing_idiots = registry.idiots()
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

        for existing_idiot in existing_idiots:
            await connections.send_message(
                existing_idiot,
                {
                    "sent_from": "moderator",
                    "message_type": "system",
                    "is_private": "no",
                    "message_content": f"{idiot.name} has entered the room.",
                    "message_age": "0 seconds"
                }
            )

        while True:
            payload = await websocket.receive_json()
            await _receive_idiot_message(
                idiot,
                payload,
                registry,
                connections,
                room
            )

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
