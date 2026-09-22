"""
Motor Max-Cut ponderado (Ising) reutilizable por la API.
Selecciona solver segun tamano: ExactSolver (optimo garantizado) o
recocido simulado (heuristico) cuando el espacio 2^n es inviable.
"""
from collections import defaultdict

import dimod


def construir_ising(enlaces: list[tuple[str, str, float]]) -> tuple[dict, dict]:
    """Acumula pesos; (u,v) y (v,u) se tratan como el mismo enlace."""
    J: dict = defaultdict(float)
    for u, v, w in enlaces:
        J[tuple(sorted((u, v)))] += float(w)
    h = {n: 0.0 for par in J for n in par}
    return h, dict(J)


def _canonicas(soluciones: list[dict], nodos: list[str]) -> list[dict]:
    vistas, salida = set(), []
    for s in soluciones:
        clave = frozenset(frozenset(n for n in nodos if s[n] == v) for v in (1, -1))
        if clave not in vistas:
            vistas.add(clave)
            salida.append(s)
    return salida


def resolver(enlaces: list[tuple[str, str, float]], params: dict) -> dict:
    h, J = construir_ising(enlaces)
    nodos = sorted(h)
    tol = float(params["tolerancia_energia"])

    if len(nodos) <= params["max_nodos_exacto"]:
        solver_usado, garantizado = "ExactSolver", True
        ss = dimod.ExactSolver().sample_ising(h, J)
    else:
        from dwave.samplers import SimulatedAnnealingSampler
        solver_usado, garantizado = "SimulatedAnnealing", False
        ss = SimulatedAnnealingSampler().sample_ising(
            h, J, num_reads=params["annealing"]["num_reads"],
            seed=params["annealing"]["seed"])

    e_min = float(ss.first.energy)
    optimas = [{k: int(v) for k, v in s.items()}
               for s, e in ss.data(["sample", "energy"]) if abs(float(e) - e_min) <= tol]
    canon = _canonicas(optimas, nodos)
    mejor = canon[0]

    total = sum(J.values())
    cortados, residuales = [], []
    for (u, v), w in sorted(J.items(), key=lambda x: -x[1]):
        destino = cortados if mejor[u] != mejor[v] else residuales
        destino.append({"nodo_origen": u, "nodo_destino": v, "peso_criticidad": w})
    mitigado = sum(e["peso_criticidad"] for e in cortados)

    zonas = params["zonas"]
    etiqueta = {1: zonas["spin_positivo"], -1: zonas["spin_negativo"]}
    return {
        "solver": solver_usado,
        "optimo_garantizado": garantizado,
        "nodos": len(nodos),
        "enlaces": len(J),
        "energia_ising": e_min,
        "segmentacion_optima": {n: etiqueta[mejor[n]] for n in nodos},
        "particiones_optimas_equivalentes": len(canon),
        "enlaces_mitigados": cortados,
        "riesgo_residual": residuales,
        "criticidad_total": total,
        "criticidad_mitigada": mitigado,
        "porcentaje_mitigado": round(100 * mitigado / total, 2) if total else 0.0,
    }
