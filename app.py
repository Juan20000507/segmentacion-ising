"""
Microservicio de segmentacion de red por Max-Cut ponderado (Ising).
Motor clasico (dimod): ExactSolver para redes pequenas, recocido simulado
para redes grandes. Parametros en config_api.json (Zero Hardcode).
"""
import json
import logging
import os
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, model_validator

import motor_maxcut

CFG = json.loads(Path(__file__).with_name("config_api.json").read_text(encoding="utf-8"))
log = logging.getLogger("maxcut_api")

app = FastAPI(
    title="Network Segmentation API (Max-Cut / Ising)",
    description=("Calcula la segmentacion de red en dos zonas que maximiza la criticidad "
                 "de los enlaces aislados. Motor clasico dimod; modelo Ising compatible "
                 "con annealers cuanticos."),
    version="1.1.0",
)


# ------------------------------------------------------------- esquemas
class EnlaceRed(BaseModel):
    nodo_origen: str = Field(min_length=1, max_length=100)
    nodo_destino: str = Field(min_length=1, max_length=100)
    peso_criticidad: float = Field(gt=0, le=CFG["peso_maximo"])

    @model_validator(mode="after")
    def sin_bucles(self):
        if self.nodo_origen == self.nodo_destino:
            raise ValueError(f"Enlace de un nodo consigo mismo: {self.nodo_origen}")
        return self


class TopologiaRed(BaseModel):
    enlaces: list[EnlaceRed] = Field(min_length=1, max_length=CFG["max_enlaces"])

    @model_validator(mode="after")
    def limite_nodos(self):
        nodos = {e.nodo_origen for e in self.enlaces} | {e.nodo_destino for e in self.enlaces}
        if len(nodos) > CFG["max_nodos_total"]:
            raise ValueError(f"{len(nodos)} nodos excede el maximo permitido "
                             f"({CFG['max_nodos_total']}).")
        return self


# ------------------------------------------------------------ seguridad
def verificar_api_key(x_api_key: str | None = Header(default=None)) -> None:
    esperada = os.environ.get(CFG["api_key_env"])
    if not esperada:
        return  # sin clave configurada: solo acceso local (host 127.0.0.1)
    if not x_api_key or not secrets.compare_digest(x_api_key, esperada):
        raise HTTPException(status_code=401, detail="API key invalida o ausente.")


# ------------------------------------------------------------ endpoints
@app.get("/api/v1/salud", summary="Estado del servicio")
def salud():
    return {"status": "OK", "max_nodos_exacto": CFG["max_nodos_exacto"],
            "max_nodos_total": CFG["max_nodos_total"]}


@app.post("/api/v1/mitigar", summary="Calcula la segmentacion de red optima",
          dependencies=[Depends(verificar_api_key)])
def calcular_segmentacion(red: TopologiaRed):
    enlaces = [(e.nodo_origen, e.nodo_destino, e.peso_criticidad) for e in red.enlaces]
    inicio = time.perf_counter()
    try:
        resultado = motor_maxcut.resolver(enlaces, CFG)
    except ImportError:
        log.exception("Solver no disponible")
        raise HTTPException(status_code=503,
                            detail="Red demasiado grande y dwave-samplers no esta instalado.")
    except Exception:
        log.exception("Fallo en el motor de optimizacion")
        raise HTTPException(status_code=500, detail="Error interno en el motor de optimizacion.")
    resultado["tiempo_ms"] = round((time.perf_counter() - inicio) * 1000, 2)
    return {"status": "SUCCESS", **resultado}
