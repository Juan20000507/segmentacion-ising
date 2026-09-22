"""
Compara solvers del modelo v4 (k zonas con reglas de convivencia), el escenario
donde el metodo clasico pierde su ventaja estructural.
Uso: python comparar_v4.py [ruta_config.json]
Salidas: resultados/solvers_v4.csv y reporte en consola.
"""
import csv
import sys
import time
from pathlib import Path

import numpy as np

import banco
import estrategias
import modelo_v4 as m4
import simulador
import topologias


def main() -> None:
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else banco.BASE / "config_banco.json"
    cfg = banco.cargar_config(ruta)
    if "v4" not in cfg["estrategias"] or "comparacion_v4" not in cfg:
        sys.exit("[ERROR] Faltan 'estrategias.v4' o 'comparacion_v4' en la configuracion")
    cv, v4 = cfg["comparacion_v4"], cfg["estrategias"]["v4"]
    salida = banco.BASE / cfg["reporte"]["carpeta"]
    salida.mkdir(exist_ok=True)
    h = int(cfg["estrategias"]["corte_riesgo"]["horizonte_inferencia"])
    q = float(cfg["estrategias"]["corte_riesgo"]["visibilidad_supuesta"])

    raiz = np.random.SeedSequence(cfg["semilla_global"]).spawn(cfg["topologias"]["cantidad"])
    instancias = []
    por_topo = int(np.ceil(cv["instancias"] / len(raiz)))
    for ss in raiz:
        rt, _, rc = [np.random.default_rng(s) for s in ss.spawn(3)]
        topo = topologias.generar(cfg, rt)
        for _ in range(por_topo):
            if len(instancias) >= cv["instancias"]:
                break
            c = simulador.preparar_corrida(topo, cfg["simulacion"], rc)
            d = simulador.hasta_deteccion(topo, c, cfg["simulacion"])
            o = simulador.observados(d, c, cfg["simulacion"]["prob_observacion"])
            instancias.append((topo, o))

    filas = []
    for n_i, (topo, o) in enumerate(instancias):
        for k in cv["zonas"]:
            ins = m4.construir_instancia(topo, o, {**v4, "zonas": k}, h, q)
            t = time.perf_counter()
            _, obj_ilp, estado = m4.resolver_ilp(topo, ins, cv["segundos_ilp"])
            t_ilp = time.perf_counter() - t
            ref = obj_ilp
            t = time.perf_counter()
            _, obj_h = m4.resolver_heuristico(topo, ins, cv["segundos_presupuesto"],
                                              np.random.default_rng(cv["semilla"] + n_i))
            t_h = time.perf_counter() - t
            t = time.perf_counter()
            _, obj_q, _ = m4.resolver_qubo(topo, ins, cv["recocido"]["num_reads"],
                                           cv["recocido"]["num_sweeps"], cv["semilla"] + n_i,
                                           cv["recocido"]["factor_penalizacion"])
            t_q = time.perf_counter() - t
            obj_q = obj_q if obj_q is not None else float("inf")
            for nombre, obj, ms in (("ILP (CBC)", obj_ilp, 1000 * t_ilp),
                                    ("Heurística clásica (ILS)", obj_h, 1000 * t_h),
                                    ("QUBO + recocido", obj_q, 1000 * t_q)):
                filas.append({"instancia": n_i, "zonas": k, "solver": nombre,
                              "estado_ilp": estado, "objetivo": obj,
                              "brecha_pct": 100 * (obj - ref) / ref if np.isfinite(obj) else float("nan"),
                              "ms": ms})
        print(f"[{n_i + 1}/{len(instancias)}]", flush=True)

    with (salida / "solvers_v4.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)

    print(f"\n{'Zonas':>6}  {'Solver':<26}{'Brecha media':>13}{'Brecha máx':>12}{'Mejor':>8}{'ms':>9}")
    print("-" * 76)
    for k in cv["zonas"]:
        for s in ("ILP (CBC)", "Heurística clásica (ILS)", "QUBO + recocido"):
            sub = [f for f in filas if f["zonas"] == k and f["solver"] == s]
            br = [f["brecha_pct"] for f in sub]
            mejor = 100 * np.mean([f["objetivo"] <= min(g["objetivo"] for g in filas
                                   if g["instancia"] == f["instancia"] and g["zonas"] == k) + 1e-9
                                   for f in sub])
            print(f"{k:>6}  {s:<26}{np.nanmean(br):>12.1f}%{np.nanmax(br):>11.1f}%"
                  f"{mejor:>7.0f}%{np.mean([f['ms'] for f in sub]):>9.0f}")
    print(f"\n[OK] {len(instancias)} instancias. Datos en {salida / 'solvers_v4.csv'}")


if __name__ == "__main__":
    main()
