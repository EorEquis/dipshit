###################
# Purpose : Bootstrap and run one D.I.P.S.H.I.T. idiot.
###################

import os
import subprocess
import sys
import venv

HERE = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(HERE, ".venv")
REQUIREMENTS = os.path.join(HERE, "requirements.txt")
IDIOT = os.path.join(HERE, "idiot.py")

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
