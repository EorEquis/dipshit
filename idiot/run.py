###################
# Purpose : Update, bootstrap, and run one D.I.P.S.H.I.T. idiot.
###################

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import venv

HERE = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(HERE, ".venv")
REQUIREMENTS = os.path.join(HERE, "requirements.txt")
IDIOT = os.path.join(HERE, "idiot.py")
DOTENV = os.path.join(HERE, ".env")
UPDATE_REF = "main"
REPO_API = "https://api.github.com/repos/EorEquis/dipshit"


def _load_update_ref():
    update_ref = os.getenv("DIPSHIT_UPDATE_REF")

    if update_ref:
        return update_ref

    try:
        with open(DOTENV, "r", encoding="utf-8") as dotenv_file:
            for raw_line in dotenv_file:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].lstrip()

                key, separator, value = line.partition("=")
                if not separator or key.strip() != "DIPSHIT_UPDATE_REF":
                    continue

                value = value.strip()
                if (
                    len(value) >= 2
                    and value[0] == value[-1]
                    and value[0] in ("'", '"')
                ):
                    value = value[1:-1]

                return value or UPDATE_REF
    except FileNotFoundError:
        pass

    return UPDATE_REF


def _fetch_json(url):
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.loads(response.read())


def _fetch_bytes(url):
    with urllib.request.urlopen(url, timeout=15) as response:
        return response.read()


def _replace_file(path, content):
    temporary_path = path + ".update"

    with open(temporary_path, "wb") as temporary_file:
        temporary_file.write(content)
        temporary_file.flush()
        os.fsync(temporary_file.fileno())

    os.replace(temporary_path, path)


def _update_client():
    update_ref = _load_update_ref()

    try:
        commit = _fetch_json(f"{REPO_API}/commits/{update_ref}")
        commit_sha = commit["sha"]
        tree = _fetch_json(
            f"{REPO_API}/git/trees/{commit_sha}?recursive=1"
        )["tree"]
    except (KeyError, json.JSONDecodeError, OSError, urllib.error.URLError) as error:
        print(f"Client update check failed: {error}")
        return False

    paths = [
        item["path"]
        for item in tree
        if item.get("type") == "blob"
        and item.get("path", "").startswith("idiot/")
        and item["path"] != "idiot/.env"
        and not item["path"].startswith("idiot/.venv/")
    ]

    updates = {}

    try:
        for repo_path in paths:
            relative_path = repo_path[len("idiot/"):]
            local_path = os.path.join(HERE, *relative_path.split("/"))
            remote = _fetch_bytes(
                "https://raw.githubusercontent.com/EorEquis/dipshit/"
                f"{commit_sha}/{repo_path}"
            )

            try:
                with open(local_path, "rb") as local_file:
                    local = local_file.read()
            except FileNotFoundError:
                local = None

            if local != remote:
                updates[local_path] = remote
    except (OSError, urllib.error.URLError) as error:
        print(f"Client update download failed: {error}")
        return False

    if not updates:
        return False

    for local_path, remote in updates.items():
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        _replace_file(local_path, remote)

    print(f"Client updated from {update_ref}; restarting bootstrap.")
    return True


if _update_client():
    os.execv(sys.executable, [sys.executable, os.path.abspath(__file__), *sys.argv[1:]])

if os.name == "nt":
    PYTHON = os.path.join(VENV, "Scripts", "python.exe")
else:
    PYTHON = os.path.join(VENV, "bin", "python")

if not os.path.exists(PYTHON):
    print("Creating virtual environment...")
    venv.EnvBuilder(with_pip=True).create(VENV)

print("Installing requirements...")
subprocess.run(
    [PYTHON, "-m", "pip", "install", "-r", REQUIREMENTS],
    check=True,
)

os.execv(PYTHON, [PYTHON, IDIOT, *sys.argv[1:]])
