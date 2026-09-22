"""Generador de topologias empresariales sinteticas por capas."""
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Topologia:
    nombres: list            # nombre de cada nodo
    capa: list               # capa de cada nodo
    valor: np.ndarray        # valor del nodo (impacto si se compromete)
    joya: np.ndarray         # bool: joya de la corona
    aristas: np.ndarray      # (m, 2) indices de nodos
    p_prop: np.ndarray       # (m,) probabilidad de propagacion por paso
    negocio: np.ndarray      # (m,) valor de negocio del enlace
    capa_arista: list        # (m,) par de capas ordenado
    adyacencia: list = field(default_factory=list)  # por nodo: [(vecino, idx_arista)]

    @property
    def n(self) -> int:
        return len(self.nombres)

    @property
    def m(self) -> int:
        return len(self.aristas)


def generar(cfg: dict, rng: np.random.Generator) -> Topologia:
    capas_cfg = cfg["topologias"]["capas"]
    nombres, capa = [], []
    for c, cant in capas_cfg.items():
        for k in range(int(cant)):
            nombres.append(f"{c[:3]}{k:02d}")
            capa.append(c)
    n = len(nombres)
    por_capa = {c: [i for i in range(n) if capa[i] == c] for c in capas_cfg}

    aristas, p_prop, negocio, capa_arista, vistos = [], [], [], [], set()

    def agregar(i, j, regla):
        clave = (min(i, j), max(i, j))
        if i == j or clave in vistos:
            return
        vistos.add(clave)
        aristas.append(clave)
        p_prop.append(rng.uniform(*regla["p_propagacion"]))
        negocio.append(rng.uniform(*regla["valor_negocio"]))
        capa_arista.append(tuple(sorted((regla["a"], regla["b"]))))

    reglas = cfg["conexiones"]
    for r in reglas:
        A, B = por_capa.get(r["a"], []), por_capa.get(r["b"], [])
        for i in A:
            for j in B:
                if r["a"] == r["b"] and j <= i:
                    continue
                if rng.random() < r["prob_enlace"]:
                    agregar(i, j, r)

    # Garantizar que ningun nodo quede aislado: se conecta segun una regla valida de su capa
    grado = np.zeros(n, dtype=int)
    for i, j in aristas:
        grado[i] += 1
        grado[j] += 1
    for i in np.where(grado == 0)[0]:
        opciones = [r for r in reglas if capa[i] in (r["a"], r["b"])]
        if not opciones:
            continue
        r = opciones[rng.integers(len(opciones))]
        otra = r["b"] if capa[i] == r["a"] else r["a"]
        candidatos = [j for j in por_capa.get(otra, []) if j != i]
        if candidatos:
            agregar(int(i), int(candidatos[rng.integers(len(candidatos))]), r)

    valor = np.array([cfg["valor_nodo"][c] for c in capa], dtype=float)
    joya = np.array([c in cfg["joyas_corona"] for c in capa])
    t = Topologia(nombres, capa, valor, joya, np.array(aristas, dtype=int),
                  np.array(p_prop), np.array(negocio), capa_arista)
    t.adyacencia = [[] for _ in range(n)]
    for e, (i, j) in enumerate(t.aristas):
        t.adyacencia[i].append((j, e))
        t.adyacencia[j].append((i, e))
    return t
