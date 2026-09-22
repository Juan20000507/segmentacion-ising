"""
Analisis de sensibilidad: repite el banco en una cuadricula de
visibilidad (prob_observacion) x rapidez de deteccion (paso_deteccion).
Uso: python sensibilidad.py [ruta_config.json]
Salidas: resultados/sensibilidad.csv, resultados/reporte_sensibilidad.html
"""
import copy
import csv
import sys
import time
from pathlib import Path

import banco
from reporte_sensibilidad import generar_html


def mejor_viable(resumen: list, techo: float) -> dict:
    viables = [f for f in resumen if f["costo_negocio_pct"] <= techo]
    return min(viables, key=lambda f: (f["joya_comprometida"], f["costo_negocio_pct"]))


def main() -> None:
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else banco.BASE / "config_banco.json"
    cfg = banco.cargar_config(ruta)
    if "sensibilidad" not in cfg:
        sys.exit("[ERROR] Falta la seccion 'sensibilidad' en la configuracion")
    sens = cfg["sensibilidad"]
    techo = float(cfg["reporte"]["techo_costo_negocio_pct"])
    salida = banco.BASE / cfg["reporte"]["carpeta"]
    salida.mkdir(exist_ok=True)

    escenarios, filas_csv = [], []
    total = len(sens["prob_observacion"]) * len(sens["paso_deteccion"])
    inicio, i = time.perf_counter(), 0
    for paso in sens["paso_deteccion"]:
        for p_obs in sens["prob_observacion"]:
            i += 1
            c = copy.deepcopy(cfg)
            c["simulacion"]["paso_deteccion"] = int(paso)
            c["simulacion"]["prob_observacion"] = float(p_obs)
            c["simulacion"]["corridas_por_topologia"] = int(sens["corridas_por_topologia"])
            if "estrategias" in sens:
                c["estrategias"]["habilitadas"] = list(sens["estrategias"])
            banco.validar(c)
            print(f"[{i}/{total}] visibilidad {p_obs:.0%}, deteccion en paso {paso}...", flush=True)
            res = banco.ejecutar(c, verbose=False)
            mejor = mejor_viable(res["resumen"], techo)
            base = next(f for f in res["resumen"] if f["estrategia"] == "ninguna")
            esc = {"prob_observacion": float(p_obs), "paso_deteccion": int(paso),
                   "pct_joya_det": res["pct_joya_det"], "resumen": res["resumen"],
                   "mejor": mejor, "base": base}
            escenarios.append(esc)
            for f in res["resumen"]:
                filas_csv.append({
                    "prob_observacion": p_obs, "paso_deteccion": paso,
                    "joya_perdida_al_detectar_pct": round(res["pct_joya_det"], 3),
                    "estrategia": f["estrategia"],
                    "viable": int(f["costo_negocio_pct"] <= techo),
                    "joya_comprometida_pct": round(f["joya_comprometida"], 3),
                    "joya_contenible_pct": round(f["joya_contenible"], 3),
                    "nodos_comprometidos": round(f["nodos_comprometidos"], 3),
                    "costo_negocio_pct": round(f["costo_negocio_pct"], 3),
                    "cortes": round(f["cortes"], 3),
                })
    duracion = time.perf_counter() - inicio

    with (salida / "sensibilidad.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas_csv[0].keys()))
        w.writeheader()
        w.writerows(filas_csv)
    (salida / "reporte_sensibilidad.html").write_text(
        generar_html(cfg, escenarios, duracion), encoding="utf-8")

    print(f"\n{'Visib.':>7}{'Paso':>6}{'Perdida al detectar':>21}{'Mejor viable':>20}{'Joya %':>8}{'Costo %':>9}")
    print("-" * 71)
    for e in escenarios:
        print(f"{e['prob_observacion']:>7.0%}{e['paso_deteccion']:>6}{e['pct_joya_det']:>20.1f}%"
              f"{e['mejor']['estrategia']:>20}{e['mejor']['joya_comprometida']:>8.1f}"
              f"{e['mejor']['costo_negocio_pct']:>9.1f}")
    print(f"\n[OK] {total} escenarios en {duracion:.0f} s. "
          f"Reporte: {salida / 'reporte_sensibilidad.html'}")


if __name__ == "__main__":
    main()
