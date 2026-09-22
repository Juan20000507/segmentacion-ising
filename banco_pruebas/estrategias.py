"""
Estrategias de contencion. Cada una recibe la topologia y los nodos observados
en el paso de deteccion, y devuelve una mascara booleana de enlaces cortados.
"""
import zlib
from collections import defaultdict

import networkx as nx
from networkx.algorithms.flow import shortest_augmenting_path
import numpy as np

from topologias import Topologia


def ninguna(topo, obs, ctx):
    return np.zeros(topo.m, dtype=bool)


def aleatoria(topo, obs, ctx):
    k = min(ctx["presupuesto"], topo.m)
    cortes = np.zeros(topo.m, dtype=bool)
    cortes[ctx["rng"].choice(topo.m, size=k, replace=False)] = True
    return cortes


def grado(topo, obs, ctx):
    """Corta los enlaces de los nodos mas conectados hasta agotar el presupuesto."""
    cortes = np.zeros(topo.m, dtype=bool)
    usados = 0
    for u in ctx["orden_grado"]:
        for _, e in topo.adyacencia[u]:
            if usados >= ctx["presupuesto"]:
                return cortes
            if not cortes[e]:
                cortes[e] = True
                usados += 1
    return cortes


def regla_estatica(topo, obs, ctx):
    return ctx["mascara_estatica"].copy()


def aislar_observados(topo, obs, ctx):
    """Aislamiento de host tipo EDR: se cortan todos los enlaces de cada nodo observado."""
    cortes = np.zeros(topo.m, dtype=bool)
    for u in np.flatnonzero(obs):
        for _, e in topo.adyacencia[u]:
            cortes[e] = True
    return cortes


def maxcut(topo, obs, ctx):
    """Modelo actual: Max-Cut ponderado por riesgo, independiente del incidente."""
    return ctx["mascara_maxcut"].copy()


def mincut(topo, obs, ctx):
    """Corte minimo de costo de negocio que separa lo observado de las joyas no observadas."""
    fuentes = set(np.flatnonzero(obs))
    sumideros = [i for i in np.flatnonzero(topo.joya) if i not in fuentes]
    if not fuentes or not sumideros:
        return np.zeros(topo.m, dtype=bool)
    # Capacidades enteras: networkx decide la particion comparando flujo == capacidad
    # de forma exacta; con flotantes hay enlaces "casi saturados" que producen
    # particiones invalidas. Se escala (mincut_escala_capacidad en config) y se usa un infinito explicito.
    esc = int(ctx["mincut_escala"])
    cap = np.rint(topo.negocio * esc).astype(np.int64) + 1
    cap_inf = int(cap.sum()) * 2 + 1
    G = nx.DiGraph()
    for e, (i, j) in enumerate(topo.aristas):
        G.add_edge(int(i), int(j), capacity=int(cap[e]))
        G.add_edge(int(j), int(i), capacity=int(cap[e]))
    for s in fuentes:
        G.add_edge("S", int(s), capacity=cap_inf)
    for t in sumideros:
        G.add_edge(int(t), "T", capacity=cap_inf)
    _, (lado_s, _) = nx.minimum_cut(G, "S", "T", flow_func=shortest_augmenting_path)
    cortes = np.zeros(topo.m, dtype=bool)
    for e, (i, j) in enumerate(topo.aristas):
        cortes[e] = (int(i) in lado_s) != (int(j) in lado_s)
    _verificar_separacion(topo, fuentes, sumideros, cortes)
    return cortes


def _verificar_separacion(topo, fuentes, sumideros, cortes):
    """Garantia: tras el corte ninguna fuente alcanza una joya protegida."""
    visto = np.zeros(topo.n, dtype=bool)
    pila = [int(s) for s in fuentes]
    visto[pila] = True
    while pila:
        u = pila.pop()
        for v, e in topo.adyacencia[u]:
            if not cortes[e] and not visto[v]:
                visto[v] = True
                pila.append(v)
    if visto[list(sumideros)].any():
        raise RuntimeError("Corte minimo invalido: una fuente sigue conectada a una joya protegida")


# ----------------------------------------------------------------------------
# Modelo v2: corte con riesgo inferido
# ----------------------------------------------------------------------------
def riesgo_inferido(topo: Topologia, obs: np.ndarray, horizonte: int, visibilidad: float) -> np.ndarray:
    """
    Probabilidad aproximada de que cada nodo este comprometido.
    1) Propagacion de campo medio desde los observados durante 'horizonte' pasos.
    2) Ajuste bayesiano: un nodo no observado es menos probable que este infectado,
       porque con visibilidad q habria sido visto con probabilidad q.
    """
    r = obs.astype(float)
    i, j, p = topo.aristas[:, 0], topo.aristas[:, 1], topo.p_prop
    for _ in range(horizonte):
        log_no = np.zeros(topo.n)
        np.add.at(log_no, j, np.log1p(-np.minimum(r[i] * p, 1 - 1e-12)))
        np.add.at(log_no, i, np.log1p(-np.minimum(r[j] * p, 1 - 1e-12)))
        r = 1 - (1 - r) * np.exp(log_no)
    q = visibilidad
    post = np.where(obs, 1.0, r * (1 - q) / np.maximum(r * (1 - q) + (1 - r), 1e-12))
    return post


def _corte_unarios(topo, fuentes, sumideros, penal_protegido, esc):
    """
    Corte de grafo con terminos unarios (resoluble exacto por flujo maximo):
    minimiza  costo de enlaces cortados + sum(penal_protegido[v] para v del lado protegido).
    Fuentes forzadas al lado de cuarentena; sumideros forzados al lado protegido.
    """
    cap = np.rint(topo.negocio * esc).astype(np.int64) + 1
    pen = np.rint(penal_protegido * esc).astype(np.int64)
    cap_inf = int(cap.sum() + pen.sum()) * 2 + 1
    G = nx.DiGraph()
    for e, (i, j) in enumerate(topo.aristas):
        G.add_edge(int(i), int(j), capacity=int(cap[e]))
        G.add_edge(int(j), int(i), capacity=int(cap[e]))
    for v in range(topo.n):
        if v in fuentes:
            G.add_edge("S", v, capacity=cap_inf)
        elif pen[v] > 0 and v not in sumideros:
            G.add_edge("S", v, capacity=int(pen[v]))   # se paga si v queda protegido
    for t in sumideros:
        G.add_edge(int(t), "T", capacity=cap_inf)
    _, (lado_s, _) = nx.minimum_cut(G, "S", "T", flow_func=shortest_augmenting_path)
    cortes = np.zeros(topo.m, dtype=bool)
    for e, (i, j) in enumerate(topo.aristas):
        cortes[e] = (int(i) in lado_s) != (int(j) in lado_s)
    _verificar_separacion(topo, fuentes, sumideros, cortes)
    return cortes


def corte_riesgo(topo, obs, ctx):
    """
    Modelo v2. Infiere el riesgo de los nodos no observados y los aparta de las joyas
    si el riesgo esperado supera el costo de negocio de cortarlos. Lambda (cuanto vale
    evitar riesgo frente a costo) se elige de forma adaptativa: el mas protector
    cuyo costo de negocio no supere el presupuesto.
    """
    cfg = ctx["v2"]
    fuentes = set(int(v) for v in np.flatnonzero(obs))
    sumideros = set(int(i) for i in np.flatnonzero(topo.joya) if int(i) not in fuentes)
    if not fuentes or not sumideros:
        return np.zeros(topo.m, dtype=bool)
    post = riesgo_inferido(topo, obs, int(cfg["horizonte_inferencia"]), float(cfg["visibilidad_supuesta"]))
    total = float(topo.negocio.sum())
    presupuesto = float(cfg["presupuesto_costo_pct"])
    lams = sorted(float(x) for x in cfg["lambdas"])

    # Busqueda binaria del lambda mas protector dentro del presupuesto.
    # Las soluciones del corte parametrico son anidadas: el costo crece con lambda.
    mejor, lo, hi = None, 0, len(lams) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        cortes = _corte_unarios(topo, fuentes, sumideros, lams[mid] * post, ctx["mincut_escala"])
        if 100 * float(topo.negocio[cortes].sum()) / total <= presupuesto:
            mejor, lo = cortes, mid + 1
        else:
            hi = mid - 1
    # Respaldo: equivale a lambda = 0. Es el minimo costo posible para separar lo
    # observado de las joyas, aunque en escenarios extremos supere el presupuesto.
    return mejor if mejor is not None else mincut(topo, obs, ctx)


def vecindario(topo, obs, ctx):
    """
    Linea base del v2: agrega como fuentes a los vecinos de lo observado conectados por
    enlaces de alta propagacion (p >= p_min) y aplica el corte minimo. Sin inferencia.
    """
    p_min = float(ctx["vecindario_p_min"])
    ext = obs.copy()
    for u in np.flatnonzero(obs):
        for v, e in topo.adyacencia[u]:
            if not topo.joya[v] and topo.p_prop[e] >= p_min:
                ext[v] = True
    return mincut(topo, ext, ctx)


# ----------------------------------------------------------------------------
# Modelo v3: corte con riesgo y limite de nodos en cuarentena (NP-hard)
# ----------------------------------------------------------------------------
# Problema:  minimizar  sum(costo de enlaces cortados) + lambda * sum(riesgo de nodos protegidos)
#            sujeto a   observados en cuarentena, joyas protegidas,
#                       como maximo K nodos adicionales en cuarentena.
# Sin el limite K es el v2 (polinomico). El limite de cardinalidad lo vuelve NP-hard.

def _instancia_v3(topo, obs, ctx):
    cfg = ctx["v3"]
    fuentes = set(int(v) for v in np.flatnonzero(obs))
    sumideros = set(int(i) for i in np.flatnonzero(topo.joya) if int(i) not in fuentes)
    post = riesgo_inferido(topo, obs, int(cfg["horizonte_inferencia"]), float(cfg["visibilidad_supuesta"]))
    return fuentes, sumideros, post, float(cfg["lambda"]), int(cfg["max_cuarentena"])


def objetivo_v3(topo, x, post, lam):
    """x: 1 = cuarentena, 0 = protegido. Devuelve el valor del objetivo."""
    corte = x[topo.aristas[:, 0]] != x[topo.aristas[:, 1]]
    return float(topo.negocio[corte].sum() + lam * post[x == 0].sum())


def _lado_cuarentena(topo, fuentes, cortes):
    lado = np.zeros(topo.n, dtype=int)
    pila = list(fuentes)
    lado[pila] = 1
    while pila:
        u = pila.pop()
        for v, e in topo.adyacencia[u]:
            if not cortes[e] and not lado[v]:
                lado[v] = 1
                pila.append(v)
    return lado


def _corte_lagrange(topo, fuentes, sumideros, post, lam, mu, esc):
    """Corte de grafo con penalizacion mu por cada nodo libre en cuarentena (sigue siendo polinomico)."""
    cap = np.rint(topo.negocio * esc).astype(np.int64) + 1
    pen_prot = np.rint(lam * post * esc).astype(np.int64)
    pen_cuar = int(round(mu * esc))
    cap_inf = int(cap.sum() + pen_prot.sum() + pen_cuar * topo.n) * 2 + 1
    G = nx.DiGraph()
    G.add_nodes_from(["S", "T"])
    for e, (i, j) in enumerate(topo.aristas):
        G.add_edge(int(i), int(j), capacity=int(cap[e]))
        G.add_edge(int(j), int(i), capacity=int(cap[e]))
    for v in range(topo.n):
        if v in fuentes:
            G.add_edge("S", v, capacity=cap_inf)
        elif v in sumideros:
            G.add_edge(v, "T", capacity=cap_inf)
        else:
            if pen_prot[v] > 0:
                G.add_edge("S", v, capacity=int(pen_prot[v]))
            if pen_cuar > 0:
                G.add_edge(v, "T", capacity=pen_cuar)
    _, (lado_s, _) = nx.minimum_cut(G, "S", "T", flow_func=shortest_augmenting_path)
    x = np.array([1 if v in lado_s else 0 for v in range(topo.n)])
    return x


def resolver_v3_lagrange(topo, obs, ctx):
    """Relajacion lagrangiana: busca la menor penalizacion mu que respeta el limite K."""
    fuentes, sumideros, post, lam, K = _instancia_v3(topo, obs, ctx)
    esc = ctx["mincut_escala"]
    libres = lambda x: int(x.sum()) - len(fuentes)
    x = _corte_lagrange(topo, fuentes, sumideros, post, lam, 0.0, esc)
    if libres(x) <= K:
        return x, objetivo_v3(topo, x, post, lam)
    lo, hi = 0.0, float(topo.negocio.sum() + lam * post.sum()) + 1.0
    mejor = _corte_lagrange(topo, fuentes, sumideros, post, lam, hi, esc)
    for _ in range(int(ctx["v3"]["lagrange_iteraciones"])):
        mid = (lo + hi) / 2
        xm = _corte_lagrange(topo, fuentes, sumideros, post, lam, mid, esc)
        if libres(xm) <= K:
            mejor, hi = xm, mid
        else:
            lo = mid
    return mejor, objetivo_v3(topo, mejor, post, lam)


def qubo_v3(topo, fuentes, sumideros, post, lam, K, factor_p=1.0):
    """
    Construye el QUBO del v3 sobre los nodos libres.
    Variables: x_v (1 = cuarentena) y bits de holgura para la restriccion sum(x) <= K.
    """
    libres = [v for v in range(topo.n) if v not in fuentes and v not in sumideros]
    Q = defaultdict(float)
    const = 0.0
    fijo = {v: 1 for v in fuentes}
    fijo.update({v: 0 for v in sumideros})
    for e, (i, j) in enumerate(topo.aristas):
        i, j, c = int(i), int(j), float(topo.negocio[e])
        if i in fijo and j in fijo:
            const += c if fijo[i] != fijo[j] else 0.0
        elif i in fijo or j in fijo:
            f, v = (i, j) if i in fijo else (j, i)
            if fijo[f] == 1:          # cortado si v queda protegido: c*(1 - x_v)
                const += c
                Q[(v, v)] -= c
            else:                     # cortado si v queda en cuarentena: c*x_v
                Q[(v, v)] += c
        else:                         # c*(x_i + x_j - 2 x_i x_j)
            Q[(i, i)] += c
            Q[(j, j)] += c
            Q[(min(i, j), max(i, j))] -= 2 * c
    for v in libres:                  # lambda * r_v * (1 - x_v)
        const += lam * post[v]
        Q[(v, v)] -= lam * post[v]
    const += lam * sum(post[v] for v in sumideros)   # joyas: siempre protegidas

    # Restriccion sum(x) + holgura = K, con bits de holgura acotados
    bits, resto, k = [], K, 0
    while resto > 0:
        b = min(2 ** k, resto)
        bits.append(b)
        resto -= b
        k += 1
    var_h = [("h", t) for t in range(len(bits))]
    terminos = [(v, 1.0) for v in libres] + list(zip(var_h, map(float, bits)))
    P = 1.0 + max((abs(Q.get((v, v), 0.0)) + sum(abs(q) for (a, b), q in Q.items()
                   if a != b and v in (a, b))) for v in libres) if libres else 1.0
    P *= factor_p
    # P * (sum a_i z_i - K)^2
    const += P * K * K
    for idx, (zi, ai) in enumerate(terminos):
        Q[(zi, zi)] += P * (ai * ai - 2 * K * ai)
        for zj, aj in terminos[idx + 1:]:
            Q[(zi, zj)] += 2 * P * ai * aj
    return dict(Q), const, libres, P


def resolver_v3_qubo(topo, obs, ctx):
    """Formulacion QUBO resuelta con recocido simulado; se conserva la mejor muestra factible."""
    from dwave.samplers import SimulatedAnnealingSampler
    fuentes, sumideros, post, lam, K = _instancia_v3(topo, obs, ctx)
    cq = ctx["v3"]["qubo"]
    Q, _, libres, _ = qubo_v3(topo, fuentes, sumideros, post, lam, K, float(cq.get("factor_penalizacion", 1.0)))
    ss = SimulatedAnnealingSampler().sample_qubo(
        Q, num_reads=int(cq["num_reads"]), num_sweeps=int(cq["num_sweeps"]),
        seed=(int(cq.get("seed", 0)) + zlib.crc32(obs.tobytes())) % (2**31))   # no altera el azar de otras estrategias
    mejor, mejor_obj = None, np.inf
    for muestra in ss.samples():
        x = np.zeros(topo.n, dtype=int)
        x[list(fuentes)] = 1
        for v in libres:
            x[v] = int(muestra[v])
        if int(x.sum()) - len(fuentes) > K:
            continue
        o = objetivo_v3(topo, x, post, lam)
        if o < mejor_obj:
            mejor, mejor_obj = x, o
    return mejor, mejor_obj


def _cortes_desde_x(topo, x):
    return x[topo.aristas[:, 0]] != x[topo.aristas[:, 1]]


def busqueda_local_v3(topo, x0, fuentes, sumideros, post, lam, K, iteraciones=200):
    """
    Control experimental: mejora una solucion del v3 con busqueda local de mejor mejora.
    Vecindario: agregar, quitar o intercambiar un nodo libre de la cuarentena.
    Sirve para distinguir el aporte de la formulacion QUBO del aporte de "un segundo metodo".
    """
    libres = [v for v in range(topo.n) if v not in fuentes and v not in sumideros]
    x = x0.copy()
    mejor = objetivo_v3(topo, x, post, lam)
    for _ in range(iteraciones):
        cand, cand_obj = None, mejor
        dentro = [v for v in libres if x[v] == 1]
        fuera = [v for v in libres if x[v] == 0]
        movimientos = [("quitar", v, None) for v in dentro]
        if len(dentro) < K:
            movimientos += [("agregar", v, None) for v in fuera]
        movimientos += [("cambiar", v, w) for v in dentro for w in fuera]
        for tipo, v, w in movimientos:
            y = x.copy()
            if tipo == "quitar":
                y[v] = 0
            elif tipo == "agregar":
                y[v] = 1
            else:
                y[v], y[w] = 0, 1
            o = objetivo_v3(topo, y, post, lam)
            if o < cand_obj - 1e-9:
                cand, cand_obj = y, o
        if cand is None:
            break
        x, mejor = cand, cand_obj
    return x, mejor


def resolver_v3_lagrange_bl(topo, obs, ctx):
    """Lagrange seguido de busqueda local (control clasico del hibrido)."""
    fuentes, sumideros, post, lam, K = _instancia_v3(topo, obs, ctx)
    x, _ = resolver_v3_lagrange(topo, obs, ctx)
    it = int(ctx["v3"].get("busqueda_local_iteraciones", 200))
    return busqueda_local_v3(topo, x, fuentes, sumideros, post, lam, K, it)


def resolver_v3_exacto(topo, obs, ctx):
    """Optimo exacto por programacion entera (CBC), sin limite practico sobre K."""
    import pulp
    fuentes, sumideros, post, lam, K = _instancia_v3(topo, obs, ctx)
    libres = [v for v in range(topo.n) if v not in fuentes and v not in sumideros]
    fijo = {v: 1 for v in fuentes}
    fijo.update({v: 0 for v in sumideros})
    p = pulp.LpProblem("v3", pulp.LpMinimize)
    X = {v: pulp.LpVariable(f"x{v}", cat="Binary") for v in libres}
    val = lambda v: X[v] if v in X else fijo[v]
    obj, const = [], 0.0
    for e, (i, j) in enumerate(topo.aristas):
        i, j, c = int(i), int(j), float(topo.negocio[e])
        if i in fijo and j in fijo:
            const += c if fijo[i] != fijo[j] else 0.0
            continue
        y = pulp.LpVariable(f"y{e}", lowBound=0, upBound=1)   # relajable: el optimo la fuerza a 0/1
        p += y >= val(i) - val(j)
        p += y >= val(j) - val(i)
        obj.append(c * y)
    for v in libres:
        const += lam * float(post[v])
        obj.append(-lam * float(post[v]) * X[v])
    const += lam * float(sum(post[v] for v in sumideros))
    p += pulp.lpSum(obj)
    p += pulp.lpSum(X.values()) <= K
    p.solve(pulp.PULP_CBC_CMD(msg=0))
    if pulp.LpStatus[p.status] != "Optimal":
        raise RuntimeError("CBC no encontro el optimo")
    x = np.zeros(topo.n, dtype=int)
    x[list(fuentes)] = 1
    for v in libres:
        x[v] = int(round(X[v].value()))
    return x, objetivo_v3(topo, x, post, lam)


def _v3_resultados(topo, obs, ctx):
    """Resuelve el v3 una sola vez por ataque y comparte el resultado entre las tres variantes."""
    clave = obs.tobytes()
    cache = ctx.setdefault("_cache_v3", {})
    if cache.get("clave") != clave:
        fuentes, sumideros, *_ = _instancia_v3(topo, obs, ctx)
        if not fuentes or not sumideros:
            cache.update(clave=clave, lag=None, qubo=None)
        else:
            cache.update(clave=clave, lag=resolver_v3_lagrange(topo, obs, ctx),
                         qubo=resolver_v3_qubo(topo, obs, ctx))
    return cache["lag"], cache["qubo"]


def v3_lagrange(topo, obs, ctx):
    lag, _ = _v3_resultados(topo, obs, ctx)
    return np.zeros(topo.m, dtype=bool) if lag is None else _cortes_desde_x(topo, lag[0])


def v3_qubo(topo, obs, ctx):
    lag, qubo = _v3_resultados(topo, obs, ctx)
    if lag is None:
        return np.zeros(topo.m, dtype=bool)
    x = qubo[0] if qubo[0] is not None else lag[0]   # sin muestra factible: respaldo clasico
    return _cortes_desde_x(topo, x)


def v3_hibrido(topo, obs, ctx):
    """Ejecuta ambos solvers y conserva la solucion de menor objetivo."""
    lag, qubo = _v3_resultados(topo, obs, ctx)
    if lag is None:
        return np.zeros(topo.m, dtype=bool)
    x = qubo[0] if qubo[0] is not None and qubo[1] < lag[1] else lag[0]
    return _cortes_desde_x(topo, x)

REGISTRO = {f.__name__: f for f in
            (ninguna, aleatoria, grado, regla_estatica, aislar_observados, maxcut, mincut,
             vecindario, corte_riesgo, v3_lagrange, v3_qubo, v3_hibrido)}


def contexto_topologia(topo: Topologia, cfg_est: dict, rng: np.random.Generator) -> dict:
    """Precalcula lo que no depende del incidente (se hace una vez por topologia)."""
    grados = np.array([len(a) for a in topo.adyacencia])
    pares = {tuple(sorted(p)) for p in cfg_est["regla_estatica"]}
    mascara_estatica = np.array([ca in pares for ca in topo.capa_arista])

    ctx = {"presupuesto": int(cfg_est["presupuesto_cortes"]),
           "mincut_escala": int(cfg_est["mincut_escala_capacidad"]),
           "v2": cfg_est.get("corte_riesgo", {}),
           "v3": cfg_est.get("v3", {}),
           "vecindario_p_min": cfg_est.get("vecindario", {}).get("p_min", 0.10),
           "orden_grado": list(np.argsort(-grados, kind="stable")),
           "mascara_estatica": mascara_estatica, "rng": rng}

    if "maxcut" in cfg_est["habilitadas"]:
        from dwave.samplers import SimulatedAnnealingSampler
        J = {}
        for e, (i, j) in enumerate(topo.aristas):
            J[(int(i), int(j))] = float(topo.p_prop[e] * max(topo.valor[i], topo.valor[j]))
        h = {i: 0.0 for i in range(topo.n)}
        ss = SimulatedAnnealingSampler().sample_ising(
            h, J, num_reads=cfg_est["maxcut"]["num_reads"], seed=cfg_est["maxcut"]["seed"])
        s = ss.first.sample
        ctx["mascara_maxcut"] = np.array([s[int(i)] != s[int(j)] for i, j in topo.aristas])
    return ctx
