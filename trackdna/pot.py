from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

NODE = Path(r"C:\Program Files\nodejs\node.exe")
POT_HOME = Path.home() / "AppData" / "Roaming" / "TrackDNA" / "bgutil-ytdlp-pot-provider" / "server"
POT_HOST = "127.0.0.1"
POT_PORT = 4416


def pot_ready() -> bool:
    try:
        with socket.create_connection((POT_HOST, POT_PORT), timeout=0.4):
            return True
    except OSError:
        return False


def ensure_pot_server(progress=None) -> bool:
    if pot_ready():
        return True
    script = POT_HOME / "build" / "main.js"
    if not NODE.exists() or not script.exists():
        return False
    if progress:
        progress("Starting YouTube token helper…")
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [str(NODE), str(script), "--port", str(POT_PORT)],
        cwd=str(POT_HOME),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation,
    )
    for _ in range(40):
        if pot_ready():
            return True
        time.sleep(0.15)
    return pot_ready()


def node_runtime() -> dict:
    return {"node": {"path": str(NODE)}} if NODE.exists() else {}
