"""
Modelo v4: segmentacion en k zonas con reglas de convivencia.
A diferencia del v2 y el v3, aqui no hay estructura de corte de grafo que explotar:
con tres o mas zonas el problema es NP-hard (corte multiterminal) y las reglas de
"no pueden convivir" son no submodulares. Es el escenario donde el metodo clasico
pierde su ventaja estructural y la comparacion con QUBO queda equilibrada.

Asignacion: zona 0 = cuarentena; zonas 1..k-1 = zonas operativas.
Objetivo (a minimizar):
    sum(costo de enlaces entre zonas distintas)
  + lambda * sum(riesgo inferido de los nodos que NO estan en cuarentena)
  + gamma * sum(pares "juntos" separados en zonas distintas)
  + delta * sum(pares "separados" que comparten zona)
Restricciones duras: observados en la zona 0; joyas fuera de la zona 0.
"""
from collections import defaultdict

import numpy as np

import estrategias


def construir_instancia(topo, obs, cfg_v4, horizonte, visibilidad):
    post = estrategias.riesgo_inferido(topo, obs, horizonte, visibilidad)
    fuentes = set(int(v) for v in np.flatnonzero(obs))
    joyas = set(int(i) for i in np.flatnonzero(topo.joya) if int(i) not in fuentes)
    pares_j = {tuple(sorted(p)) for p in cfg_v4["juntos"]}
    pares_s = {tuple(sorted(p)) for p in cfg_v4["separados"]}
    juntos = [(int(i), int(j)) for e, (i, j) in enumerate(topo.aristas)
              if topo.capa_arista[e] in pares_j]
    if cfg_v4.get("dominios"):
        # Version escalable: en lugar de prohibir pares (cuadratico), se restringe
        # el conjunto de zonas permitidas por capa (lineal en el numero de nodos).
        separados = []
    else:
        separados = [(int(i), int(j)) for i in range(topo.n) for j in range(i + 1, topo.n)
                     if tuple(sorted((topo.capa[i], topo.capa[j]))) in pares_s]
    k = int(cfg_v4["zonas"])
    dom = cfg_v4.get("dominios") or {}
    dominio = [tuple(z for z in dom.get(topo.capa[v], range(k)) if z < k) or tuple(range(k))
               for v in range(topo.n)]
    return {"post": post, "fuentes": fuentes, "joyas": joyas, "juntos": juntos,
            "separados": separados, "dominio": dominio, "k": k,
            "lambda": float(cfg_v4["lambda"]), "gamma": float(cfg_v4["gamma"]),
            "delta": float(cfg_v4["delta"])}


def objetivo_v4(topo, z, ins) -> float:
    """z: vector de zona por nodo. Devuelve el costo total (penaliza lo infactible)."""
    corte = z[topo.aristas[:, 0]] != z[topo.aristas[:, 1]]
    total = float(topo.negocio[corte].sum())
    total += ins["lambda"] * float(ins["post"][z != 0].sum())
    total += ins["gamma"] * sum(1 for i, j in ins["juntos"] if z[i] != z[j])
    total += ins["delta"] * sum(1 for i, j in ins["separados"] if z[i] == z[j])
    total += ins["delta"] * sum(1 for v in range(topo.n) if z[v] not in ins["dominio"][v])
    return total


def factible(z, ins) -> bool:
    return (all(z[v] == 0 for v in ins["fuentes"]) and all(z[v] != 0 for v in ins["joyas"]))


def _libres(topo, ins):
    return [v for v in range(topo.n) if v not in ins["fuentes"] and v not in ins["joyas"]]


# ------------------------------------------------------------------ solvers
def resolver_ilp(topo, ins, segundos: float):
    """Optimo exacto (o mejor cota) con programacion entera."""
    import time as _t

    import pulp
    k = ins["k"]
    p = pulp.LpProblem("v4", pulp.LpMinimize)
    X = {(v, z): pulp.LpVariable(f"x_{v}_{z}", cat="Binary")
         for v in range(topo.n) for z in range(k)}
    for v in range(topo.n):
        p += pulp.lpSum(X[(v, z)] for z in range(k)) == 1
    for v in ins["fuentes"]:
        p += X[(v, 0)] == 1
    for v in ins["joyas"]:
        p += X[(v, 0)] == 0
    for v in range(topo.n):
        for z in range(k):
            if z not in ins["dominio"][v]:
                p += X[(v, z)] == 0
    obj = []
    for e, (i, j) in enumerate(topo.aristas):
        i, j = int(i), int(j)
        y = pulp.LpVariable(f"y_{e}", lowBound=0, upBound=1)
        for z in range(k):
            p += y >= X[(i, z)] - X[(j, z)]
        obj.append(float(topo.negocio[e]) * y)
    for v in range(topo.n):
        obj.append(ins["lambda"] * float(ins["post"][v]) * (1 - X[(v, 0)]))
    for n, (i, j) in enumerate(ins["juntos"]):
        d = pulp.LpVariable(f"d_{n}", lowBound=0, upBound=1)
        for z in range(k):
            p += d >= X[(i, z)] - X[(j, z)]
        obj.append(ins["gamma"] * d)
    for n, (i, j) in enumerate(ins["separados"]):
        for z in range(k):
            s = pulp.LpVariable(f"s_{n}_{z}", lowBound=0, upBound=1)
            p += s >= X[(i, z)] + X[(j, z)] - 1
            obj.append(ins["delta"] * s)
    p += pulp.lpSum(obj)
    t0 = _t.perf_counter()
    p.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=segundos))
    transcurrido = _t.perf_counter() - t0
    # PuLP reporta "Optimal" aunque CBC se haya detenido por limite de tiempo:
    # solo se considera optimo probado si termino holgadamente antes del limite.
    estado = pulp.LpStatus[p.status]
    if estado == "Optimal" and transcurrido > 0.95 * segundos:
        estado = "Limite de tiempo"
    z = np.zeros(topo.n, dtype=int)
    for v in range(topo.n):
        for zz in range(k):
            if X[(v, zz)].value() and round(X[(v, zz)].value()) == 1:
                z[v] = zz
    return z, objetivo_v4(topo, z, ins), estado


def _zonas(ins, v, inicio, k):
    """Zonas permitidas para el nodo v (dominio de su capa), desde 'inicio'."""
    return tuple(z for z in ins["dominio"][v] if z >= inicio) or tuple(range(inicio, k))


def _busqueda_local(topo, z, ins, libres):
    """Mejor mejora sobre movimientos de un nodo de zona."""
    k = ins["k"]
    mejora = True
    while mejora:
        mejora = False
        actual = objetivo_v4(topo, z, ins)
        for v in libres:
            z0 = z[v]
            inicio = 1 if v in ins["joyas"] else 0
            mejor_z, mejor_o = z0, actual
            for zz in _zonas(ins, v, inicio, k):
                if zz == z0:
                    continue
                z[v] = zz
                o = objetivo_v4(topo, z, ins)
                if o < mejor_o - 1e-9:
                    mejor_z, mejor_o = zz, o
            z[v] = mejor_z
            if mejor_z != z0:
                actual, mejora = mejor_o, True
    return z, objetivo_v4(topo, z, ins)


def resolver_heuristico(topo, ins, segundos, rng, perturbacion=4):
    """
    Control clasico: busqueda local iterada (voraz + mejora local + perturbaciones),
    con el mismo presupuesto de tiempo que se le da al recocido.
    """
    import time as _t
    k = ins["k"]
    libres = [v for v in range(topo.n) if v not in ins["fuentes"]]
    z = np.zeros(topo.n, dtype=int)
    for v in ins["joyas"]:
        z[v] = 1
    for v in [v for v in libres if v not in ins["joyas"]]:     # construccion voraz
        opciones = _zonas(ins, v, 0, k)
        costos = []
        for zz in opciones:
            z[v] = zz
            costos.append(objetivo_v4(topo, z, ins))
        z[v] = opciones[int(np.argmin(costos))]
    z, obj = _busqueda_local(topo, z, ins, libres)
    mejor, mejor_obj = z.copy(), obj
    fin = _t.perf_counter() + segundos
    while _t.perf_counter() < fin:                              # perturbar y reoptimizar
        z = mejor.copy()
        for v in rng.choice(libres, size=min(perturbacion, len(libres)), replace=False):
            inicio = 1 if int(v) in ins["joyas"] else 0
            opciones = _zonas(ins, int(v), inicio, k)
            z[int(v)] = int(opciones[rng.integers(len(opciones))])
        z, obj = _busqueda_local(topo, z, ins, libres)
        if obj < mejor_obj:
            mejor, mejor_obj = z.copy(), obj
    return mejor, mejor_obj


def construir_qubo(topo, ins, factor_p=4.0):
    """QUBO con codificacion one-hot: x[v,z] = 1 si el nodo v va a la zona z."""
    k = ins["k"]
    idx = lambda v, z: v * k + z
    Q = defaultdict(float)
    const = 0.0

    def add(a, b, w):
        Q[(min(a, b), max(a, b))] += w

    for e, (i, j) in enumerate(topo.aristas):   # costo de corte: c*(1 - sum_z x_iz x_jz)
        i, j, c = int(i), int(j), float(topo.negocio[e])
        const += c
        for z in range(k):
            add(idx(i, z), idx(j, z), -c)
    for v in range(topo.n):                     # riesgo si no esta en cuarentena
        const += ins["lambda"] * float(ins["post"][v])
        add(idx(v, 0), idx(v, 0), -ins["lambda"] * float(ins["post"][v]))
    for i, j in ins["juntos"]:                  # gamma si quedan en zonas distintas
        const += ins["gamma"]
        for z in range(k):
            add(idx(i, z), idx(j, z), -ins["gamma"])
    for i, j in ins["separados"]:               # delta si comparten zona
        for z in range(k):
            add(idx(i, z), idx(j, z), ins["delta"])

    escala = max(abs(w) for w in Q.values()) if Q else 1.0
    P = float(factor_p) * escala
    for v in range(topo.n):                     # una sola zona por nodo
        const += P
        for z in range(k):
            add(idx(v, z), idx(v, z), -P)
            for z2 in range(z + 1, k):
                add(idx(v, z), idx(v, z2), 2 * P)
    for v in ins["fuentes"]:                    # observados en cuarentena
        add(idx(v, 0), idx(v, 0), -P)
        const += P
    for v in ins["joyas"]:                      # joyas fuera de la cuarentena
        add(idx(v, 0), idx(v, 0), P)
    for v in range(topo.n):                     # zonas no permitidas por capa
        for z in range(k):
            if z not in ins["dominio"][v]:
                add(idx(v, z), idx(v, z), P)
    return dict(Q), const, P


def _reparar(muestra, topo, ins):
    """
    Decodifica una muestra del QUBO a una asignacion valida.
    Si un nodo no tiene exactamente una zona activa, se elige la de menor costo local;
    despues se imponen las restricciones duras (observados, joyas y dominios).
    """
    k = ins["k"]
    z = np.zeros(topo.n, dtype=int)
    rotos = 0
    for v in range(topo.n):
        activos = [zz for zz in range(k) if muestra[v * k + zz] == 1]
        permitidas = ins["dominio"][v]
        if len(activos) == 1 and activos[0] in permitidas:
            z[v] = activos[0]
            continue
        rotos += 1
        cand = [a for a in activos if a in permitidas] or list(permitidas)
        z[v] = cand[0]
    for v in ins["fuentes"]:
        z[v] = 0
    for v in ins["joyas"]:
        if z[v] == 0:
            alt = [zz for zz in ins["dominio"][v] if zz != 0]
            z[v] = alt[0] if alt else 1
    return z, rotos


def resolver_qubo(topo, ins, num_reads, num_sweeps, semilla, factor_p=4.0):
    """Recocido simulado sobre el QUBO, con reparacion de las muestras no validas."""
    from dwave.samplers import SimulatedAnnealingSampler
    Q, _, _ = construir_qubo(topo, ins, factor_p)
    ss = SimulatedAnnealingSampler().sample_qubo(
        Q, num_reads=int(num_reads), num_sweeps=int(num_sweeps), seed=int(semilla))
    mejor, mejor_obj, limpias = None, np.inf, 0
    for muestra in ss.samples():
        z, rotos = _reparar(muestra, topo, ins)
        limpias += (rotos == 0)
        o = objetivo_v4(topo, z, ins)
        if o < mejor_obj:
            mejor, mejor_obj = z, o
    return mejor, mejor_obj, limpias / max(1, int(num_reads))
