"""
Simulador de propagacion por pasos (cascada independiente con reintentos).
Numeros aleatorios comunes: todas las estrategias enfrentan exactamente el mismo
ataque hasta el paso de deteccion y los mismos sorteos despues.
"""
import numpy as np

from topologias import Topologia


def preparar_corrida(topo: Topologia, cfg_sim: dict, rng: np.random.Generator) -> dict:
    entradas = [i for i in range(topo.n) if topo.capa[i] in cfg_sim["capas_entrada"]]
    return {
        "entrada": int(entradas[rng.integers(len(entradas))]),
        "U": rng.random((cfg_sim["pasos_totales"], topo.m)),   # sorteos de contagio
        "V": rng.random(topo.n),                                # sorteos de observacion
    }


def _paso(topo, infectado, activo, U_t):
    nuevos = []
    for u in np.flatnonzero(infectado):
        for v, e in topo.adyacencia[u]:
            if not infectado[v] and activo[e] and U_t[e] < topo.p_prop[e]:
                nuevos.append(v)
    if nuevos:
        infectado[nuevos] = True


def hasta_deteccion(topo: Topologia, corrida: dict, cfg_sim: dict) -> np.ndarray:
    infectado = np.zeros(topo.n, dtype=bool)
    infectado[corrida["entrada"]] = True
    activo = np.ones(topo.m, dtype=bool)
    for t in range(cfg_sim["paso_deteccion"]):
        _paso(topo, infectado, activo, corrida["U"][t])
    return infectado


def observados(infectado: np.ndarray, corrida: dict, p_obs: float) -> np.ndarray:
    obs = infectado & (corrida["V"] < p_obs)
    if not obs.any():
        obs = np.zeros_like(infectado)
        obs[corrida["entrada"]] = True   # la alerta inicial siempre existe
    return obs


def despues_contencion(topo, corrida, cfg_sim, infectado_det, cortes: np.ndarray) -> np.ndarray:
    infectado = infectado_det.copy()
    activo = ~cortes
    for t in range(cfg_sim["paso_deteccion"], cfg_sim["pasos_totales"]):
        _paso(topo, infectado, activo, corrida["U"][t])
    return infectado
