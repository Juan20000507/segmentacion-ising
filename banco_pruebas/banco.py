"""
Banco de pruebas: compara estrategias de contencion sobre topologias sinteticas.
Uso: python banco.py [ruta_config.json]
Salidas: resultados/corridas.csv, resultados/resumen.csv, resultados/reporte_banco.html
La funcion ejecutar() es reutilizada por sensibilidad.py.
"""
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

import estrategias
import simulador
import topologias

BASE = Path(__file__).resolve().parent
REQUERIDAS = ("semilla_global", "topologias", "valor_nodo", "joyas_corona",
              "conexiones", "simulacion", "estrategias", "reporte")
METRICAS = ["joya_comprometida", "nodos_comprometidos", "valor_comprometido_pct",
            "cortes", "costo_negocio_pct"]


def cargar_config(ruta: Path) -> dict:
    if not ruta.exists():
        sys.exit(f"[ERROR] No existe la configuracion: {ruta}")
    cfg = json.loads(ruta.read_text(encoding="utf-8"))
    faltan = [k for k in REQUERIDAS if k not in cfg]
    if faltan:
        sys.exit(f"[ERROR] Faltan claves en {ruta.name}: {', '.join(faltan)}")
    validar(cfg)
    return cfg


def validar(cfg: dict) -> None:
    desconocidas = [e for e in cfg["estrategias"]["habilitadas"] if e not in estrategias.REGISTRO]
    if desconocidas:
        sys.exit(f"[ERROR] Estrategias desconocidas: {', '.join(desconocidas)}")
    sim = cfg["simulacion"]
    if not 0 < sim["paso_deteccion"] < sim["pasos_totales"]:
        sys.exit("[ERROR] paso_deteccion debe estar entre 1 y pasos_totales - 1")
    if not 0 <= sim["prob_observacion"] <= 1:
        sys.exit("[ERROR] prob_observacion debe estar entre 0 y 1")
    capas = set(cfg["topologias"]["capas"])
    for r in cfg["conexiones"]:
        if r["a"] not in capas or r["b"] not in capas:
            sys.exit(f"[ERROR] Conexion con capa inexistente: {r['a']}-{r['b']}")
    if not set(sim["capas_entrada"]) <= capas:
        sys.exit("[ERROR] capas_entrada contiene capas inexistentes")
    for k in ("carpeta", "nivel_confianza_z", "techo_costo_negocio_pct"):
        if k not in cfg["reporte"]:
            sys.exit(f"[ERROR] Falta reporte.{k} en la configuracion")


def ejecutar(cfg: dict, verbose: bool = True) -> dict:
    sim, cfg_est = cfg["simulacion"], cfg["estrategias"]
    nombres_est = cfg_est["habilitadas"]
    raiz = np.random.SeedSequence(cfg["semilla_global"])
    filas, info_topos = [], []
    inicio = time.perf_counter()

    for k, ss in enumerate(raiz.spawn(cfg["topologias"]["cantidad"])):
        rng_topo, rng_est, rng_corr = [np.random.default_rng(s) for s in ss.spawn(3)]
        topo = topologias.generar(cfg, rng_topo)
        ctx = estrategias.contexto_topologia(topo, cfg_est, rng_est)
        negocio_total = float(topo.negocio.sum())
        valor_total = float(topo.valor.sum())
        info_topos.append({"topologia": k, "nodos": topo.n, "enlaces": topo.m,
                           "joyas": int(topo.joya.sum())})
        if verbose:
            print(f"[INFO] Topologia {k}: {topo.n} nodos, {topo.m} enlaces, "
                  f"{int(topo.joya.sum())} joyas", flush=True)

        for r in range(sim["corridas_por_topologia"]):
            corrida = simulador.preparar_corrida(topo, sim, rng_corr)
            inf_det = simulador.hasta_deteccion(topo, corrida, sim)
            obs = simulador.observados(inf_det, corrida, sim["prob_observacion"])
            joya_ya = bool((inf_det & topo.joya).any())
            for nombre in nombres_est:
                cortes = estrategias.REGISTRO[nombre](topo, obs, ctx)
                inf_fin = simulador.despues_contencion(topo, corrida, sim, inf_det, cortes)
                filas.append({
                    "topologia": k, "corrida": r, "estrategia": nombre,
                    "joya_en_deteccion": int(joya_ya),
                    "joya_comprometida": int((inf_fin & topo.joya).any()),
                    "nodos_comprometidos": int(inf_fin.sum()),
                    "valor_comprometido_pct": 100 * float(topo.valor[inf_fin].sum()) / valor_total,
                    "cortes": int(cortes.sum()),
                    "costo_negocio_pct": 100 * float(topo.negocio[cortes].sum()) / negocio_total,
                })

    duracion = time.perf_counter() - inicio
    resumen = resumir(filas, nombres_est, len(info_topos), float(cfg["reporte"]["nivel_confianza_z"]))
    base = [f for f in filas if f["estrategia"] == nombres_est[0]]
    pct_joya_det = 100 * float(np.mean([f["joya_en_deteccion"] for f in base]))
    return {"filas": filas, "resumen": resumen, "info_topos": info_topos,
            "pct_joya_det": pct_joya_det, "duracion": duracion}


def _media_ic(x: np.ndarray, z: float) -> tuple[float, float]:
    if len(x) == 0:
        return 0.0, 0.0
    ic = float(z * x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else 0.0
    return float(x.mean()), ic


def resumir(filas: list, nombres_est: list, n_topos: int, z: float) -> list:
    resumen = []
    for nombre in nombres_est:
        sub = [f for f in filas if f["estrategia"] == nombre]
        fila = {"estrategia": nombre, "n": len(sub)}
        for mtr in METRICAS:
            x = np.array([f[mtr] for f in sub], dtype=float)
            if mtr == "joya_comprometida":
                x = 100 * x
            fila[mtr], fila[mtr + "_ic"] = _media_ic(x, z)
        cont = 100 * np.array([f["joya_comprometida"] for f in sub if not f["joya_en_deteccion"]], dtype=float)
        fila["joya_contenible"], fila["joya_contenible_ic"] = _media_ic(cont, z)
        fila["n_contenibles"] = len(cont)
        fila["joya_por_topologia"] = [
            100 * float(np.mean([f["joya_comprometida"] for f in sub if f["topologia"] == k]))
            for k in range(n_topos)]
        resumen.append(fila)
    return resumen


def main() -> None:
    from reporte import generar_html

    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "config_banco.json"
    cfg = cargar_config(ruta)
    salida = BASE / cfg["reporte"]["carpeta"]
    salida.mkdir(exist_ok=True)

    res = ejecutar(cfg)
    filas, resumen = res["filas"], res["resumen"]

    with (salida / "corridas.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    with (salida / "resumen.csv").open("w", newline="", encoding="utf-8") as f:
        campos = [c for c in resumen[0] if c != "joya_por_topologia"]
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(resumen)

    html = generar_html(cfg, resumen, res["info_topos"], res["pct_joya_det"], res["duracion"])
    (salida / "reporte_banco.html").write_text(html, encoding="utf-8")

    print(f"\n{'Estrategia':<20}{'Joya %':>8}{'Contenible %':>14}{'Nodos':>8}{'Negocio %':>11}{'Cortes':>8}")
    print("-" * 69)
    for f in resumen:
        print(f"{f['estrategia']:<20}{f['joya_comprometida']:>8.1f}{f['joya_contenible']:>14.1f}"
              f"{f['nodos_comprometidos']:>8.1f}{f['costo_negocio_pct']:>11.1f}{f['cortes']:>8.1f}")
    print(f"\n[INFO] Joya ya comprometida al detectar: {res['pct_joya_det']:.1f}% de las corridas")
    print(f"[OK] {len(filas)} simulaciones en {res['duracion']:.1f} s. "
          f"Reporte: {salida / 'reporte_banco.html'}")


if __name__ == "__main__":
    main()
