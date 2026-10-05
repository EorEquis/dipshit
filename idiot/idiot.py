###################
# Created : 2026-10-03 GB
# Purpose : Connects one physical idiot to the D.I.P.S.H.I.T. moderator.
# Notes   : Keeps one llama.cpp process alive and transcribes individual turns.
###################

import asyncio
import json
import os
import socket

import websockets


CTX_SIZE = os.getenv("DIPSHIT_CTX_SIZE", "4096")
LLAMA = os.path.expanduser(
    os.getenv("DIPSHIT_LLAMA", "~/llama.cpp/build/bin/llama-cli")
)
MODEL = os.path.expanduser(
    os.getenv("DIPSHIT_MODEL", "~/models/Qwen3-1.7B-Q4_K_M.gguf")
)
MODERATOR = os.getenv("DIPSHIT_MODERATOR", "ws://mousenas:8080/ws/idiot")
NAME = os.getenv("DIPSHIT_NAME", socket.gethostname().upper())

PERSONALITY = {
    "curiosity": int(os.getenv("DIPSHIT_CURIOSITY", "75")),
    "friendliness": int(os.getenv("DIPSHIT_FRIENDLINESS", "50")),
    "sociability": int(os.getenv("DIPSHIT_SOCIABILITY", "25"))
}


async def _read_turn(websocket, process, process_started=False):
    recent = ""
    speaking = False
    tracing = not process_started

    while True:
        chunk = await process.stdout.read(1)

        if not chunk:
            return_code = await process.wait()

            await websocket.send(
                json.dumps(
                    {
                        "content": (
                            f"\n[llama-cli exited unexpectedly with code "
                            f"{return_code}]\n"
                        ),
                        "type": "trace"
                    }
                )
            )

            raise RuntimeError(
                f"llama-cli exited unexpectedly with code {return_code}"
            )

        content = chunk.decode("utf-8", errors="replace")
        recent = (recent + content)[-64:]

        if not tracing:
            if "[Start thinking]" not in recent:
                continue

            tracing = True
            content = "[Start thinking]"
            recent = content

        await websocket.send(
            json.dumps(
                {
                    "content": content,
                    "type": "trace"
                }
            )
        )

        if not speaking and "[End thinking]" in recent:
            await websocket.send(
                json.dumps({"state": "SPEAKING", "type": "state"})
            )
            speaking = True
            recent = ""

        if speaking and recent.endswith("\n> "):
            await websocket.send(
                json.dumps({"state": "IDLE", "type": "state"})
            )
            return


async def _run_inference(websocket, process, prompt):
    await websocket.send(json.dumps({"state": "THINKING", "type": "state"}))

    process_started = process is None

    if process_started:
        process = await asyncio.create_subprocess_exec(
            LLAMA,
            "-m",
            MODEL,
            "--ctx-size",
            CTX_SIZE,
            "--context-shift",
            "--simple-io",
            "-p",
            prompt,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
    else:
        if process.returncode is not None:
            raise RuntimeError(
                f"llama-cli is not running (code {process.returncode})"
            )

        process.stdin.write((prompt + "\n").encode("utf-8"))
        await process.stdin.drain()

    await _read_turn(websocket, process, process_started)

    return process


async def main():
    process = None

    async with websockets.connect(MODERATOR) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "name": NAME,
                    "personality": PERSONALITY,
                    "type": "connect"
                }
            )
        )

        acknowledgement = json.loads(await websocket.recv())

        if acknowledgement.get("type") != "connected":
            raise RuntimeError(acknowledgement)

        print(
            f'{acknowledgement["name"]} connected '
            f'({acknowledgement["connection_id"]})'
        )

        async for raw_message in websocket:
            message = json.loads(raw_message)

            if message.get("type") == "prompt":
                process = await _run_inference(
                    websocket,
                    process,
                    message["prompt"]
                )


if __name__ == "__main__":
    asyncio.run(main())
