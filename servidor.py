"""Lanzador: verifica puerto libre, abre Swagger y arranca uvicorn."""
import json
import socket
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

CFG = json.loads(Path(__file__).with_name("config_api.json").read_text(encoding="utf-8"))
HOST, PUERTO = CFG["host"], int(CFG["puerto"])

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    if s.connect_ex((HOST, PUERTO)) == 0:
        sys.exit(f"[ERROR] El puerto {PUERTO} ya esta en uso por otro servicio. "
                 "Cambia 'puerto' en config_api.json.")

url = f"http://{HOST}:{PUERTO}/docs"
print(f"[OK] API en {url}  (Ctrl+C para detener)")
if CFG.get("abrir_navegador"):
    threading.Timer(2.0, lambda: webbrowser.open(url)).start()
uvicorn.run("app:app", host=HOST, port=PUERTO, log_level="info")
