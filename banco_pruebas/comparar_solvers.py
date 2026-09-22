"""
Compara solvers del modelo v3 contra el optimo exacto (fuerza bruta).
Pregunta: la formulacion QUBO resuelta por recocido aporta frente al metodo clasico?
Uso: python comparar_solvers.py [ruta_config.json]
Salidas: resultados/solvers.csv, resultados/reporte_solvers.html
"""
import copy
import csv
import sys
import time
from pathlib import Path

import numpy as np

import banco
import estrategias
import simulador
import topologias
from reporte_solvers import generar_html


def prueba_pareada(a, b):
    """Wilcoxon de rangos con signo sobre las brechas pareadas (a - b)."""
    from scipy.stats import wilcoxon
    d = np.array(a) - np.array(b)
    if np.allclose(d, 0):
        return 1.0, 0, 0
    gana_b = int((d > 1e-9).sum())     # b mejor que a
    gana_a = int((d < -1e-9).sum())
    try:
        p = float(wilcoxon(d, zero_method="wilcox").pvalue)
    except ValueError:
        p = 1.0
    return p, gana_a, gana_b


def main() -> None:
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else banco.BASE / "config_banco.json"
    cfg = banco.cargar_config(ruta)
    if "comparacion_solvers" not in cfg or "v3" not in cfg["estrategias"]:
        sys.exit("[ERROR] Faltan las secciones 'comparacion_solvers' o 'estrategias.v3'")
    cs = cfg["comparacion_solvers"]
    salida = banco.BASE / cfg["reporte"]["carpeta"]
    salida.mkdir(exist_ok=True)

    # Instancias: ataques reales del simulador, en varias topologias
    raiz = np.random.SeedSequence(cfg["semilla_global"]).spawn(cfg["topologias"]["cantidad"])
    instancias = []
    por_topo = int(np.ceil(cs["instancias"] / len(raiz)))
    for ss in raiz:
        rt, re, rc = [np.random.default_rng(s) for s in ss.spawn(3)]
        topo = topologias.generar(cfg, rt)
        cfg_est = {**cfg["estrategias"], "habilitadas": []}
        ctx = estrategias.contexto_topologia(topo, cfg_est, re)
        tomadas = 0
        while tomadas < por_topo and len(instancias) < cs["instancias"]:
            c = simulador.preparar_corrida(topo, cfg["simulacion"], rc)
            d = simulador.hasta_deteccion(topo, c, cfg["simulacion"])
            o = simulador.observados(d, c, cfg["simulacion"]["prob_observacion"])
            if estrategias._instancia_v3(topo, o, ctx)[1]:
                instancias.append((topo, o, ctx))
                tomadas += 1

    filas, inicio = [], time.perf_counter()
    for K in cs["limites_cuarentena"]:
        print(f"[INFO] Limite de cuarentena K = {K}", flush=True)
        for n_i, (topo, o, ctx) in enumerate(instancias):
            ctx = copy.copy(ctx)
            ctx["v3"] = {**cfg["estrategias"]["v3"], "max_cuarentena": int(K)}
            fuentes, sumideros, post, lam, _ = estrategias._instancia_v3(topo, o, ctx)
            n_libres = topo.n - len(fuentes) - len(sumideros)
            n_vars = n_libres + int(np.ceil(np.log2(K + 1)))

            t = time.perf_counter()
            _, opt = estrategias.resolver_v3_exacto(topo, o, ctx)
            t_exacto = time.perf_counter() - t
            filas.append({"K": K, "instancia": n_i, "solver": "Exacto (CBC)", "variables_qubo": n_vars,
                          "objetivo": opt, "optimo": opt, "factible": 1, "ms": 1000 * t_exacto})

            t = time.perf_counter()
            _, o_lag = estrategias.resolver_v3_lagrange(topo, o, ctx)
            t_lag = time.perf_counter() - t
            filas.append({"K": K, "instancia": n_i, "solver": "Lagrange", "variables_qubo": n_vars,
                          "objetivo": o_lag, "optimo": opt, "factible": 1, "ms": 1000 * t_lag})

            t = time.perf_counter()
            _, o_bl = estrategias.resolver_v3_lagrange_bl(topo, o, ctx)
            t_bl = time.perf_counter() - t
            filas.append({"K": K, "instancia": n_i, "solver": "Lagrange + búsqueda local",
                          "variables_qubo": n_vars, "objetivo": o_bl, "optimo": opt,
                          "factible": 1, "ms": 1000 * t_bl})

            for conf in cs["configuraciones_recocido"]:
                ctx["v3"] = {**ctx["v3"], "qubo": {**cfg["estrategias"]["v3"]["qubo"], **conf}}
                t = time.perf_counter()
                _, o_q = estrategias.resolver_v3_qubo(topo, o, ctx)
                t_q = time.perf_counter() - t
                nombre = f"Recocido {conf['num_reads']}x{conf['num_sweeps']}"
                fact = int(np.isfinite(o_q))
                filas.append({"K": K, "instancia": n_i, "solver": nombre, "variables_qubo": n_vars,
                              "objetivo": o_q if fact else o_lag, "optimo": opt, "factible": fact,
                              "ms": 1000 * t_q})
                filas.append({"K": K, "instancia": n_i, "solver": f"Híbrido (Lagrange + {nombre})",
                              "variables_qubo": n_vars, "objetivo": min(o_lag, o_q if fact else np.inf),
                              "optimo": opt, "factible": 1, "ms": 1000 * (t_lag + t_q)})
    duracion = time.perf_counter() - inicio

    for f in filas:
        f["brecha_pct"] = 100 * (f["objetivo"] - f["optimo"]) / f["optimo"] if f["optimo"] > 0 else 0.0
        f["es_optimo"] = int(f["brecha_pct"] < 1e-6)
    with (salida / "solvers.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    # Pruebas pareadas: el aporte del recocido frente al control clasico
    pruebas = []
    ref = "Lagrange + búsqueda local"
    for K in cs["limites_cuarentena"]:
        g = lambda s: [f["brecha_pct"] for f in filas if f["K"] == K and f["solver"] == s]
        for s in dict.fromkeys(f["solver"] for f in filas):
            if s in (ref, "Exacto (CBC)"):
                continue
            p, gana_s, gana_ref = prueba_pareada(g(s), g(ref))
            pruebas.append({"K": K, "solver": s, "referencia": ref, "p": p,
                            "gana_solver": gana_s, "gana_referencia": gana_ref})
    with (salida / "pruebas_pareadas.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(pruebas[0].keys()))
        w.writeheader()
        w.writerows(pruebas)
    (salida / "reporte_solvers.html").write_text(generar_html(cfg, filas, duracion, pruebas), encoding="utf-8")

    print(f"\n{'K':>3}  {'Solver':<42}{'Brecha media':>13}{'Optimo':>9}{'Factible':>10}{'ms':>8}")
    print("-" * 86)
    for K in cs["limites_cuarentena"]:
        for s in dict.fromkeys(f["solver"] for f in filas):
            sub = [f for f in filas if f["K"] == K and f["solver"] == s]
            print(f"{K:>3}  {s:<42}{np.mean([f['brecha_pct'] for f in sub]):>12.2f}%"
                  f"{100*np.mean([f['es_optimo'] for f in sub]):>8.0f}%"
                  f"{100*np.mean([f['factible'] for f in sub]):>9.0f}%{np.mean([f['ms'] for f in sub]):>8.0f}")
    print(f"\n[OK] {len(instancias)} instancias en {duracion:.0f} s. Reporte: {salida / 'reporte_solvers.html'}")


if __name__ == "__main__":
    main()
