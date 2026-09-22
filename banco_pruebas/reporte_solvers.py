"""Reporte HTML de la comparacion de solvers del v3."""
import html
from datetime import datetime

import numpy as np


def _e(x):
    return html.escape(str(x))


def _agregado(filas):
    Ks = sorted({f["K"] for f in filas})
    solvers = list(dict.fromkeys(f["solver"] for f in filas))
    tabla = {}
    for K in Ks:
        for s in solvers:
            sub = [f for f in filas if f["K"] == K and f["solver"] == s]
            tabla[(K, s)] = {
                "brecha": float(np.mean([f["brecha_pct"] for f in sub])),
                "brecha_max": float(np.max([f["brecha_pct"] for f in sub])),
                "optimo": 100 * float(np.mean([f["es_optimo"] for f in sub])),
                "factible": 100 * float(np.mean([f["factible"] for f in sub])),
                "ms": float(np.mean([f["ms"] for f in sub])),
                "vars": float(np.mean([f["variables_qubo"] for f in sub])),
            }
    return Ks, solvers, tabla


def _barras(Ks, solvers, tabla):
    W, L, R, fila = 720, 300, 60, 22
    grupos = len(Ks)
    H = 20 + grupos * (len(solvers) * fila + 26) + 30
    X = lambda v: L + v / 100 * (W - L - R)
    g, y = [], 16
    for v in (0, 25, 50, 75, 100):
        g.append(f'<line x1="{X(v):.0f}" x2="{X(v):.0f}" y1="10" y2="{H-30}" class="rej"/>'
                 f'<text x="{X(v):.0f}" y="{H-14}" text-anchor="middle" class="eje">{v}%</text>')
    for K in Ks:
        g.append(f'<text x="8" y="{y+12}" class="grupo">Máximo {K} nodo{"s" if K > 1 else ""} en cuarentena</text>')
        y += 20
        for s in solvers:
            t = tabla[(K, s)]
            clase = "b-lag" if s == "Lagrange" else ("b-hib" if s.startswith("Híbrido") else "b-sa")
            g.append(f'<text x="{L-8}" y="{y+13}" text-anchor="end" class="eje">{_e(s)}</text>'
                     f'<rect x="{L}" y="{y+2}" width="{X(t["optimo"])-L:.1f}" height="{fila-8}" rx="3" class="{clase}"/>'
                     f'<text x="{X(t["optimo"])+6:.1f}" y="{y+13}" class="val">{t["optimo"]:.0f}%</text>')
            y += fila
        y += 6
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Porcentaje de instancias resueltas al óptimo por solver">{"".join(g)}</svg>'


def generar_html(cfg, filas, duracion, pruebas=None):
    Ks, solvers, tabla = _agregado(filas)
    cs = cfg["comparacion_solvers"]
    n_inst = len({(f["instancia"]) for f in filas})
    n_k = len(Ks)
    vars_med = np.mean([f["variables_qubo"] for f in filas])

    solvers = [s for s in solvers if s != "Exacto (CBC)"]
    sa = [s for s in solvers if s.startswith("Recocido")]
    hib = [s for s in solvers if s.startswith("Híbrido")]
    opt_lag = np.mean([tabla[(K, "Lagrange")]["optimo"] for K in Ks])
    opt_sa = max(np.mean([tabla[(K, s)]["optimo"] for K in Ks]) for s in sa) if sa else 0
    opt_hib = max(np.mean([tabla[(K, s)]["optimo"] for K in Ks]) for s in hib) if hib else 0
    ms_lag = np.mean([tabla[(K, "Lagrange")]["ms"] for K in Ks])
    ms_sa = min(np.mean([tabla[(K, s)]["ms"] for K in Ks]) for s in sa) if sa else 0

    if opt_lag >= opt_sa + 5:
        t1 = "El método clásico supera al recocido sobre QUBO."
    elif opt_sa >= opt_lag + 5:
        t1 = "El recocido sobre QUBO supera al método clásico."
    else:
        t1 = "El método clásico y el recocido sobre QUBO rinden parecido."
    t2 = ("Combinarlos sí aporta." if opt_hib >= max(opt_lag, opt_sa) + 3
          else "Combinarlos aporta poco.")

    ref = "Lagrange + búsqueda local"
    opt_bl = np.mean([tabla[(K, ref)]["optimo"] for K in Ks]) if (Ks and (Ks[0], ref) in tabla) else 0
    if pruebas:
        sig = [p for p in pruebas if p["solver"].startswith("Híbrido") and p["p"] < 0.05 and p["gana_solver"] > p["gana_referencia"]]
        if sig:
            t3 = (f"El aporte del recocido sobre QUBO sobrevive al control clásico: el híbrido mejora de forma "
                  f"significativa a «{ref}» en {len(sig)} de los {len(Ks)} límites evaluados (Wilcoxon, p &lt; 0,05).")
        else:
            t3 = (f"El control clásico explica el aporte: «{ref}» iguala al híbrido, sin diferencias significativas "
                  f"a favor de este último (Wilcoxon, p ≥ 0,05). La mejora no es atribuible a la formulación QUBO.")
        filas_p = "".join(
            f'<tr><td>{p["K"]}</td><td>{_e(p["solver"])}</td><td>{p["gana_solver"]}</td><td>{p["gana_referencia"]}</td>'
            f'<td>{p["p"]:.4f}</td></tr>' for p in pruebas)
        seccion_p = (f'<h2>Control clásico y pruebas pareadas</h2>'
                     f'<p>Para distinguir el aporte de la formulación QUBO del aporte de «usar un segundo método», '
                     f'se añadió un control puramente clásico: la solución lagrangiana mejorada con búsqueda local. '
                     f'La tabla compara cada solver contra ese control sobre las mismas instancias, con la prueba de '
                     f'Wilcoxon de rangos con signo aplicada a las brechas pareadas.</p>'
                     f'<div class="tabla"><table><thead><tr><th>K</th><th>Solver</th><th>Instancias en que gana el solver</th>'
                     f'<th>Instancias en que gana el control</th><th>p</th></tr></thead><tbody>{filas_p}</tbody></table></div>')
    else:
        t3, seccion_p = "", ""
    filas_t = []
    for K in Ks:
        for s in solvers:
            t = tabla[(K, s)]
            filas_t.append(f'<tr><td>{K}</td><td>{_e(s)}</td><td>{t["brecha"]:.2f}%</td><td>{t["brecha_max"]:.2f}%</td>'
                           f'<td>{t["optimo"]:.0f}%</td><td>{t["factible"]:.0f}%</td><td>{t["ms"]:.0f}</td></tr>')

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Comparación de solvers del modelo v3</title>
<style>
:root{{--fondo:#EDF0F3;--papel:#F8F9FA;--tinta:#17222C;--tinta-2:#4A5864;--regla:#C7CFD6;--cobre:#B5692F;--cobalto:#2C58A0;--ok:#2F7A55;
--sans:"Segoe UI",system-ui,-apple-system,sans-serif;--serif:Georgia,"Times New Roman",serif;box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--fondo:#121A21;--papel:#18222B;--tinta:#E4E9EE;--tinta-2:#A3B0BB;--regla:#2E3C48;--cobre:#D98A4E;--cobalto:#6E97DB;--ok:#5DB889}}}}
:root[data-theme="dark"]{{--fondo:#121A21;--papel:#18222B;--tinta:#E4E9EE;--tinta-2:#A3B0BB;--regla:#2E3C48;--cobre:#D98A4E;--cobalto:#6E97DB;--ok:#5DB889}}
*,*::before,*::after{{box-sizing:inherit}}
body{{margin:0;background:var(--fondo);color:var(--tinta);font-family:var(--serif);line-height:1.6}}
main{{max-width:1000px;margin:0 auto;padding:2.5rem 1.2rem 4rem}}
h1,h2,table{{font-family:var(--sans)}}
h1{{font-size:clamp(1.7rem,4vw,2.4rem);line-height:1.1;margin:.3rem 0 .8rem;letter-spacing:-.02em}}
h2{{font-size:1.3rem;margin:2.6rem 0 .8rem}}
p,ul{{max-width:70ch}} li{{margin-bottom:.45rem}}
.meta{{font-family:var(--sans);font-size:.9rem;color:var(--tinta-2)}}
.lectura{{background:var(--papel);border-left:3px solid var(--cobalto);padding:1rem 1.3rem;margin:1.5rem 0;max-width:74ch}}
.lectura p:last-child{{margin-bottom:0}}
.panel{{background:var(--papel);border:1px solid var(--regla);border-radius:12px;padding:1.2rem;overflow-x:auto}}
svg{{width:100%;height:auto;display:block;min-width:600px}}
svg .rej{{stroke:var(--regla)}} svg .eje{{fill:var(--tinta-2);font:12px var(--sans)}}
svg .grupo{{fill:var(--tinta);font:600 13px var(--sans)}} svg .val{{fill:var(--tinta);font:600 12px var(--sans)}}
svg .b-lag{{fill:var(--cobalto)}} svg .b-sa{{fill:var(--cobre)}} svg .b-hib{{fill:var(--ok)}}
.tabla{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%;font-size:.88rem;font-variant-numeric:tabular-nums}}
th,td{{text-align:left;padding:.5rem .5rem;border-bottom:1px solid var(--regla)}}
th{{font-weight:500;color:var(--tinta-2);font-size:.8rem}}
footer{{margin-top:3rem;border-top:1px solid var(--regla);padding-top:.8rem;font-family:var(--sans);font-size:.8rem;color:var(--tinta-2)}}
</style></head><body><main>
<p class="meta">Comparación de solvers, generado el {datetime.now():%Y-%m-%d %H:%M}</p>
<h1>¿Aporta la formulación QUBO al modelo v3?</h1>
<p>El v3 agrega al v2 un límite al número de nodos que se pueden poner en cuarentena. Esa restricción vuelve el problema NP-hard, que es el terreno donde QUBO e Ising tienen sentido. Aquí se comparan, sobre {n_inst} ataques simulados y {n_k} límites de cuarentena, la relajación lagrangiana, esa misma solución mejorada con búsqueda local, la formulación QUBO resuelta por recocido simulado y el híbrido, contra el óptimo exacto calculado con programación entera (CBC).</p>

<div class="lectura">
<p><b>{t1}</b> En promedio, la relajación lagrangiana encuentra el óptimo en el {opt_lag:.0f}% de las instancias y el mejor recocido en el {opt_sa:.0f}%, con {ms_lag:.0f} ms frente a {ms_sa:.0f} ms por instancia.</p>
<p><b>{t2}</b> El híbrido, que ejecuta ambos y conserva el mejor resultado, llega al óptimo en el {opt_hib:.0f}% de los casos, frente al {opt_bl:.0f}% del control clásico («{ref}»).</p>
<p><b>{t3}</b></p>
<p><b>Escala frente al hardware actual.</b> Cada instancia necesita unas {vars_med:.0f} variables QUBO. El sistema analógico de Qilimanjaro en el BSC tiene 10 cúbits; los annealers comerciales de mayor escala requerirían además mapear el problema sobre su conectividad física.</p>
</div>

<h2>Instancias resueltas al óptimo</h2>
<div class="panel">{_barras(Ks, solvers, tabla)}</div>

{seccion_p}

<h2>Detalle por límite de cuarentena</h2>
<div class="tabla"><table>
<thead><tr><th>K</th><th>Solver</th><th>Brecha media</th><th>Brecha máxima</th><th>Óptimo</th><th>Factible</th><th>ms por instancia</th></tr></thead>
<tbody>{"".join(filas_t)}</tbody></table></div>

<h2>Cómo leer estos resultados</h2>
<ul>
<li>La brecha es cuánto peor es el objetivo de cada solver frente al óptimo exacto (costo de negocio más riesgo esperado ponderado por λ = {cfg["estrategias"]["v3"]["lambda"]:g}).</li>
<li>"Factible" indica si el recocido produjo al menos una muestra que respeta el límite de cuarentena; si no, se usa el resultado clásico.</li>
<li>El recocido simulado es un solver clásico que imita el recocido cuántico. Un buen desempeño aquí no demuestra ventaja cuántica, y uno malo no la descarta: indica cómo se comporta la formulación QUBO con un solver de recocido.</li>
<li>El óptimo exacto se calcula con un solver de programación entera (CBC), verificado contra enumeración exhaustiva en instancias pequeñas.</li>
<li>La prueba de Wilcoxon de rangos con signo compara las brechas de dos solvers sobre las mismas instancias; un valor de p bajo indica que la diferencia no se explica por azar.</li>
</ul>
<footer>Semilla global {cfg["semilla_global"]}. Límites evaluados: {", ".join(str(k) for k in Ks)}. {duracion:.0f} s en total. Datos en solvers.csv.</footer>
</main></body></html>"""
