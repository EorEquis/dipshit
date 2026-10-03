###################
# Created : 2026-10-03 GB
# Purpose : Connects one physical idiot to the D.I.P.S.H.I.T. moderator.
# Notes   : This first client supports manual prompts and streams raw llama.cpp output.
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


async def _run_inference(websocket, prompt):
    await websocket.send(json.dumps({"state": "THINKING", "type": "state"}))

    process = await asyncio.create_subprocess_exec(
        LLAMA,
        "-m",
        MODEL,
        "--ctx-size",
        CTX_SIZE,
        "--context-shift",
        "-p",
        prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL
    )

    recent = ""

    while True:
        chunk = await process.stdout.read(1)

        if not chunk:
            break

        content = chunk.decode("utf-8", errors="replace")
        recent = (recent + content)[-64:]

        await websocket.send(
            json.dumps(
                {
                    "content": content,
                    "type": "trace"
                }
            )
        )

        if "[End thinking]" in recent:
            await websocket.send(
                json.dumps({"state": "SPEAKING", "type": "state"})
            )
            recent = ""

    return_code = await process.wait()

    if return_code != 0:
        await websocket.send(
            json.dumps(
                {
                    "content": f"\n[llama-cli exited with code {return_code}]\n",
                    "type": "trace"
                }
            )
        )

    await websocket.send(json.dumps({"state": "IDLE", "type": "state"}))


async def main():
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
                await _run_inference(websocket, message["prompt"])


if __name__ == "__main__":
    asyncio.run(main())
