"""
Escalamiento del modelo v4: hasta donde llega cada solver cuando la red crece.
Las topologias se escalan manteniendo el grado medio (se multiplica el tamano de
cada capa y se divide la densidad de enlaces).
Uso: python comparar_escala.py [ruta_config.json]
Salidas: resultados/escala.csv y resumen en consola.
"""
import copy
import csv
import sys
import time
from pathlib import Path

import numpy as np

import banco
import modelo_v4 as m4
import simulador
import topologias


def escalar(cfg: dict, F: float) -> dict:
    c = copy.deepcopy(cfg)
    for capa in c["topologias"]["capas"]:
        c["topologias"]["capas"][capa] = max(1, int(round(c["topologias"]["capas"][capa] * F)))
    for r in c["conexiones"]:
        r["prob_enlace"] = min(1.0, r["prob_enlace"] / F)
    return c


def guardar(salida: Path, filas: list) -> None:
    """Escribe los resultados parciales: una corrida larga no se pierde si se interrumpe."""
    with (salida / "escala.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)


def main() -> None:
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else banco.BASE / "config_banco.json"
    cfg = banco.cargar_config(ruta)
    ce, v4 = cfg["comparacion_escala"], cfg["estrategias"]["v4"]
    salida = banco.BASE / cfg["reporte"]["carpeta"]
    salida.mkdir(exist_ok=True)
    h = int(cfg["estrategias"]["corte_riesgo"]["horizonte_inferencia"])
    q = float(cfg["estrategias"]["corte_riesgo"]["visibilidad_supuesta"])

    filas = []
    for paso in ce["escalas"]:
        F, presupuesto = float(paso["factor"]), float(paso["segundos"])
        c = escalar(cfg, F)
        for n_i in range(int(ce["instancias"])):
            rng = np.random.default_rng(ce["semilla"] + n_i)
            topo = topologias.generar(c, rng)
            corrida = simulador.preparar_corrida(topo, c["simulacion"], rng)
            det = simulador.hasta_deteccion(topo, corrida, c["simulacion"])
            obs = simulador.observados(det, corrida, c["simulacion"]["prob_observacion"])
            ins = m4.construir_instancia(topo, obs, v4, h, q)
            print(f"[F={F:g}] instancia {n_i + 1}/{ce['instancias']}: "
                  f"{topo.n} nodos, {topo.m} enlaces, {len(ins['separados'])} pares restringidos",
                  flush=True)

            res = {}
            t = time.perf_counter()
            _, obj_ilp, estado = m4.resolver_ilp(topo, ins, float(paso["segundos_ilp"]))
            res["ILP (CBC)"] = (obj_ilp, time.perf_counter() - t, estado)

            t = time.perf_counter()
            _, obj_h = m4.resolver_heuristico(topo, ins, presupuesto, rng)
            res["Heurística clásica (ILS)"] = (obj_h, time.perf_counter() - t, "")

            t = time.perf_counter()
            _, obj_q, limpias = m4.resolver_qubo(topo, ins, paso["num_reads"], paso["num_sweeps"],
                                                 ce["semilla"] + n_i, ce["factor_penalizacion"])
            res["QUBO + recocido"] = (obj_q, time.perf_counter() - t, f"{100 * limpias:.0f}% válidas")

            mejor = min(v[0] for v in res.values() if np.isfinite(v[0]))
            for nombre, (obj, seg, nota) in res.items():
                filas.append({"factor": F, "nodos": topo.n, "enlaces": topo.m,
                              "variables_qubo": topo.n * ins["k"], "instancia": n_i,
                              "solver": nombre, "objetivo": obj, "nota": nota,
                              "brecha_vs_mejor_pct": 100 * (obj - mejor) / mejor, "s": seg})
            guardar(salida, filas)

    guardar(salida, filas)

    print(f"\n{'Nodos':>7}{'Vars':>7}  {'Solver':<26}{'Brecha vs mejor':>17}{'s':>8}")
    print("-" * 68)
    for paso in ce["escalas"]:
        F = float(paso["factor"])
        sub_f = [f for f in filas if f["factor"] == F]
        for s in ("ILP (CBC)", "Heurística clásica (ILS)", "QUBO + recocido"):
            sub = [f for f in sub_f if f["solver"] == s]
            print(f"{np.mean([f['nodos'] for f in sub]):>7.0f}"
                  f"{np.mean([f['variables_qubo'] for f in sub]):>7.0f}  {s:<26}"
                  f"{np.mean([f['brecha_vs_mejor_pct'] for f in sub]):>16.1f}%"
                  f"{np.mean([f['s'] for f in sub]):>8.1f}")
    print(f"\n[OK] Datos en {salida / 'escala.csv'}")


if __name__ == "__main__":
    main()
