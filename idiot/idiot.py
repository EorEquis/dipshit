###################
# Created : 2026-10-03 GB
# Purpose : Connects one physical idiot to the D.I.P.S.H.I.T. moderator.
# Notes   : Keeps one llama.cpp process alive and transcribes individual turns.
###################

import asyncio
import codecs
import json
import os
import socket
import sys
import urllib.error
import urllib.request

import websockets


CTX_SIZE = os.getenv("DIPSHIT_CTX_SIZE", "4096")
LLAMA = os.path.expanduser(
    os.getenv("DIPSHIT_LLAMA", "~/llama.cpp/build/bin/llama-cli")
)
MODEL = os.path.expanduser(
    os.getenv("DIPSHIT_MODEL", "~/models/Qwen3-1.7B-Q4_K_M.gguf")
)
MODERATOR = os.getenv("DIPSHIT_MODERATOR", "ws://mousenas:8080/ws/idiot")
NAME = os.getenv("DIPSHIT_NAME", socket.gethostname())
UPDATE_REF = os.getenv("DIPSHIT_UPDATE_REF", "main")
UPDATE_URL = (
    "https://raw.githubusercontent.com/EorEquis/dipshit/"
    f"{UPDATE_REF}/idiot/idiot.py"
)

PERSONALITY = {
    "curiosity": int(os.getenv("DIPSHIT_CURIOSITY", "75")),
    "friendliness": int(os.getenv("DIPSHIT_FRIENDLINESS", "50")),
    "sociability": int(os.getenv("DIPSHIT_SOCIABILITY", "25"))
}


def _update_client():
    current_path = os.path.abspath(__file__)

    try:
        with urllib.request.urlopen(UPDATE_URL, timeout=10) as response:
            updated_code = response.read()
    except (OSError, urllib.error.URLError) as error:
        print(f"Client update check failed: {error}")
        return

    try:
        with open(current_path, "rb") as current_file:
            current_code = current_file.read()
    except OSError as error:
        print(f"Could not read current client for update check: {error}")
        return

    if updated_code == current_code:
        return

    temporary_path = current_path + ".update"

    try:
        with open(temporary_path, "wb") as temporary_file:
            temporary_file.write(updated_code)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, current_path)
    except OSError as error:
        try:
            os.remove(temporary_path)
        except OSError:
            pass

        print(f"Client update failed: {error}")
        return

    print(f"Client updated from {UPDATE_REF}; restarting.")
    os.execv(sys.executable, [sys.executable, current_path, *sys.argv[1:]])


async def _read_turn(websocket, process, process_started=False):
    recent = ""
    speaking = False
    speech_buffer = ""
    speech_id = None
    tracing = not process_started
    trace_buffer = ""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

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

        content = decoder.decode(chunk)

        if not content:
            continue

        recent = (recent + content)[-64:]

        if not tracing:
            if "[Start thinking]" not in recent:
                continue

            tracing = True
            content = "[Start thinking]"
            recent = content

        trace_buffer += content

        if not speaking and speech_id is not None:
            if trace_buffer.endswith("\n> "):
                trace_buffer = trace_buffer[:-3]
            elif len(trace_buffer) <= len("\n> "):
                trace_buffer = trace_buffer
            else:
                trace_content = trace_buffer[:-2]
                trace_buffer = trace_buffer[-2:]

                await websocket.send(
                    json.dumps(
                        {
                            "content": trace_content,
                            "type": "trace"
                        }
                    )
                )
        elif trace_buffer:
            await websocket.send(
                json.dumps(
                    {
                        "content": trace_buffer,
                        "type": "trace"
                    }
                )
            )
            trace_buffer = ""

        if speaking:
            speech_buffer += content

            if "\n[ Prompt:" in speech_buffer:
                speech_content, speech_buffer = speech_buffer.split(
                    "\n[ Prompt:",
                    1
                )

                if speech_content:
                    await websocket.send(
                        json.dumps(
                            {
                                "content": speech_content,
                                "speech_id": speech_id,
                                "type": "speech_chunk"
                            }
                        )
                    )

                await websocket.send(
                    json.dumps(
                        {
                            "speech_id": speech_id,
                            "type": "speech_end"
                        }
                    )
                )
                speaking = False
            elif len(speech_buffer) > len("\n[ Prompt:"):
                keep = len("\n[ Prompt:") - 1
                speech_content = speech_buffer[:-keep]
                speech_buffer = speech_buffer[-keep:]

                await websocket.send(
                    json.dumps(
                        {
                            "content": speech_content,
                            "speech_id": speech_id,
                            "type": "speech_chunk"
                        }
                    )
                )

        if not speaking and "[End thinking]" in recent:
            await websocket.send(
                json.dumps({"state": "SPEAKING", "type": "state"})
            )
            speaking = True
            speech_id = os.urandom(8).hex()
            await websocket.send(
                json.dumps(
                    {
                        "speech_id": speech_id,
                        "type": "speech_start"
                    }
                )
            )
            recent = ""

        if not speaking and speech_id is not None and recent.endswith("\n> "):
            if trace_buffer:
                await websocket.send(
                    json.dumps(
                        {
                            "content": trace_buffer,
                            "type": "trace"
                        }
                    )
                )

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
                prompt = message["prompt"]
                print("\n========== RECEIVED FROM MODERATOR ==========")
                json_start = prompt.find('{"messages":')
                if json_start >= 0:
                    prefix = prompt[:json_start].rstrip()
                    if prefix:
                        print(prefix)
                        print()
                    try:
                        payload = json.loads(prompt[json_start:])
                        print(json.dumps(payload, indent=2))
                    except json.JSONDecodeError:
                        print(prompt[json_start:])
                else:
                    print(prompt)
                print("=============================================\n")

                process = await _run_inference(
                    websocket,
                    process,
                    message["prompt"]
                )


if __name__ == "__main__":
    print("D.I.P.S.H.I.T. idiot client self-update confirmed.")
    _update_client()
    asyncio.run(main())
