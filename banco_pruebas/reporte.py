"""Genera el reporte HTML autocontenido del banco de pruebas."""
import html
from datetime import datetime

ETIQUETAS = {
    "ninguna": ("Sin contención", "Línea base: el ataque sigue libre."),
    "aleatoria": ("Cortes aleatorios", "Corta enlaces al azar hasta el presupuesto."),
    "grado": ("Nodos más conectados", "Corta enlaces de los nodos con más conexiones, hasta el presupuesto."),
    "regla_estatica": ("Regla estática", "Corta siempre los mismos pares de capas, sin mirar el incidente."),
    "aislar_observados": ("Aislar observados", "Aislamiento tipo EDR: desconecta cada nodo donde se vio el ataque."),
    "maxcut": ("Max-Cut actual", "El modelo v1 del prototipo: dos zonas que maximizan el riesgo cortado."),
    "mincut": ("Corte mínimo", "Separa lo observado de las joyas con el menor costo de negocio (flujo máximo)."),
    "vecindario": ("Vecindario de alto riesgo", "Aísla también a los vecinos de lo observado por enlaces de alta propagación. Sin inferencia."),
    "corte_riesgo": ("Corte con riesgo (v2)", "Infiere qué nodos no vistos están comprometidos y los aparta de las joyas dentro de un presupuesto de costo."),
    "v3_lagrange": ("v3 clásico (Lagrange)", "Como el v2, pero con máximo de nodos en cuarentena; resuelto por relajación lagrangiana."),
    "v3_qubo": ("v3 QUBO (recocido)", "El mismo problema del v3 formulado como QUBO y resuelto por recocido simulado."),
    "v3_hibrido": ("v3 híbrido", "Ejecuta ambos solvers del v3 y conserva la mejor solución."),
}


def _e(x):
    return html.escape(str(x))


def viable(f, techo):
    return f["costo_negocio_pct"] <= techo


def _significativas(resumen, techo):
    """Estrategias viables cuya mejora frente a 'ninguna' supera los intervalos de confianza."""
    base = next((f for f in resumen if f["estrategia"] == "ninguna"), None)
    if base is None:
        return [f for f in resumen if viable(f, techo)]
    return [f for f in resumen if f is not base and viable(f, techo) and
            base["joya_contenible"] - f["joya_contenible"] > base["joya_contenible_ic"] + f["joya_contenible_ic"]]


def _pareto(resumen, techo):
    """Entre las estrategias viables con mejora significativa, las no dominadas en (costo, joya)."""
    candidatas = _significativas(resumen, techo)
    ef = []
    for a in candidatas:
        dominada = any(
            b is not a and b in candidatas and b["costo_negocio_pct"] <= a["costo_negocio_pct"]
            and b["joya_contenible"] <= a["joya_contenible"]
            and (b["costo_negocio_pct"] < a["costo_negocio_pct"] or b["joya_contenible"] < a["joya_contenible"])
            for b in resumen)
        if not dominada:
            ef.append(a["estrategia"])
    return ef


def _grafica(resumen, eficientes, techo):
    W, H, L, R, T, B = 720, 380, 60, 24, 20, 50
    xmax = max(100.0, max(f["costo_negocio_pct"] for f in resumen))
    X = lambda v: L + v / xmax * (W - L - R)
    Y = lambda v: T + (100 - v) / 100 * (H - T - B)
    g = []
    for v in range(0, 101, 20):
        g.append(f'<line x1="{L}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" class="rej"/>'
                 f'<text x="{L-8}" y="{Y(v)+4:.1f}" text-anchor="end" class="eje">{v}%</text>')
    for v in range(0, int(xmax) + 1, 20):
        g.append(f'<text x="{X(v):.1f}" y="{H-B+18}" text-anchor="middle" class="eje">{v}%</text>')
    g.append(f'<text x="{(L+W-R)/2}" y="{H-8}" text-anchor="middle" class="tit">Costo de negocio interrumpido</text>')
    g.append(f'<text transform="translate(14,{(T+H-B)/2}) rotate(-90)" text-anchor="middle" class="tit">'
             f'Joya comprometida (corridas contenibles)</text>')
    g.append(f'<text x="{L+8}" y="{H-B-10}" class="ideal">Zona ideal: poco costo, pocas joyas perdidas</text>')
    if techo < xmax:
        g.append(f'<rect x="{X(techo):.1f}" y="{T}" width="{W-R-X(techo):.1f}" height="{H-T-B}" class="nozona"/>'
                 f'<line x1="{X(techo):.1f}" x2="{X(techo):.1f}" y1="{T}" y2="{H-B}" class="techo"/>'
                 f'<text x="{W-R-8:.1f}" y="{H-B-10}" text-anchor="end" class="techo-t">Costo no aceptable (&gt; {techo:g}%)</text>')
    colocadas = []  # cajas de etiquetas ya ubicadas: (x0, x1, y)

    def libre(x0, x1, yy):
        return all(x1 < a or x0 > b or abs(yy - c) >= 15 for a, b, c in colocadas)

    puntos = sorted(resumen, key=lambda f: (f["joya_contenible"], f["costo_negocio_pct"]), reverse=True)
    for f in puntos:
        x, y = X(f["costo_negocio_pct"]), Y(f["joya_contenible"])
        clase = "pt ef" if f["estrategia"] in eficientes else ("pt nv" if not viable(f, techo) else "pt")
        etiqueta = ETIQUETAS.get(f["estrategia"], (f["estrategia"],))[0]
        ancho = 7.2 * len(etiqueta)
        ancla = "end" if x > W * 0.72 else "start"
        dx = -10 if ancla == "end" else 10
        x0 = x + dx - (ancho if ancla == "end" else 0)
        for desp in (-8, 20, -24, 36, -40, 52, 68, 84):
            yy = y + desp
            if libre(x0, x0 + ancho, yy):
                break
        colocadas.append((x0, x0 + ancho, yy))
        g.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{Y(max(0,f["joya_contenible"]-f["joya_contenible_ic"])):.1f}" '
                 f'y2="{Y(min(100,f["joya_contenible"]+f["joya_contenible_ic"])):.1f}" class="ic"/>')
        g.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" class="{clase}"><title>{_e(etiqueta)}</title></circle>')
        g.append(f'<text x="{x+dx:.1f}" y="{yy:.1f}" text-anchor="{ancla}" class="lab">{_e(etiqueta)}</text>')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Costo de negocio contra joyas comprometidas por estrategia">{"".join(g)}</svg>'


def generar_html(cfg, resumen, info_topos, pct_joya_det, duracion):
    sim, est = cfg["simulacion"], cfg["estrategias"]
    techo = float(cfg["reporte"]["techo_costo_negocio_pct"])
    eficientes = _pareto(resumen, techo)
    base = next((f for f in resumen if f["estrategia"] == "ninguna"), None)
    nodos_prom = sum(t["nodos"] for t in info_topos) / len(info_topos)
    enlaces_prom = sum(t["enlaces"] for t in info_topos) / len(info_topos)
    n_cont = resumen[0]["n_contenibles"]

    filas = []
    for f in resumen:
        et, desc = ETIQUETAS.get(f["estrategia"], (f["estrategia"], ""))
        marca = ' class="ef"' if f["estrategia"] in eficientes else ""
        if not viable(f, techo):
            desc = desc + " No viable: supera el techo de costo."
        red = ""
        if base and f is not base and base["joya_contenible"] > 0:
            red = f'{100 * (base["joya_contenible"] - f["joya_contenible"]) / base["joya_contenible"]:.0f}%'
        filas.append(
            f'<tr{marca}><td><b>{_e(et)}</b><small>{_e(desc)}</small></td>'
            f'<td>{f["joya_contenible"]:.1f} <i>± {f["joya_contenible_ic"]:.1f}</i></td>'
            f'<td>{red}</td>'
            f'<td>{f["joya_comprometida"]:.1f}</td>'
            f'<td>{f["nodos_comprometidos"]:.1f}</td>'
            f'<td>{f["costo_negocio_pct"]:.1f}</td>'
            f'<td>{f["cortes"]:.0f}</td></tr>')

    cab_topo = "".join(f"<th>T{t['topologia']}</th>" for t in info_topos)
    filas_topo = "".join(
        f'<tr><td>{_e(ETIQUETAS.get(f["estrategia"], (f["estrategia"],))[0])}</td>'
        + "".join(f"<td>{v:.0f}</td>" for v in f["joya_por_topologia"]) + "</tr>"
        for f in resumen)
    lista_ef = ", ".join(_e(ETIQUETAS.get(e, (e,))[0]) for e in eficientes)

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Banco de pruebas v1: resultados</title>
<style>
:root{{--fondo:#EDF0F3;--papel:#F8F9FA;--tinta:#17222C;--tinta-2:#4A5864;--regla:#C7CFD6;--cobre:#B5692F;--cobalto:#2C58A0;--cobalto-suave:#D8E2F2;--riesgo:#A23B30;--ok:#2F7A55;
--sans:"Segoe UI",system-ui,-apple-system,sans-serif;--serif:Georgia,"Times New Roman",serif;box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--fondo:#121A21;--papel:#18222B;--tinta:#E4E9EE;--tinta-2:#A3B0BB;--regla:#2E3C48;--cobre:#D98A4E;--cobalto:#6E97DB;--cobalto-suave:#1E2C44;--riesgo:#E07466;--ok:#5DB889}}}}
:root[data-theme="dark"]{{--fondo:#121A21;--papel:#18222B;--tinta:#E4E9EE;--tinta-2:#A3B0BB;--regla:#2E3C48;--cobre:#D98A4E;--cobalto:#6E97DB;--cobalto-suave:#1E2C44;--riesgo:#E07466;--ok:#5DB889}}
*,*::before,*::after{{box-sizing:inherit}}
body{{margin:0;background:var(--fondo);color:var(--tinta);font-family:var(--serif);line-height:1.6}}
main{{max-width:1040px;margin:0 auto;padding:2.5rem 1.2rem 4rem}}
h1,h2,.ui,table{{font-family:var(--sans)}}
h1{{font-size:clamp(1.7rem,4vw,2.5rem);line-height:1.1;margin:.3rem 0 .8rem;letter-spacing:-.02em}}
h2{{font-size:1.3rem;margin:2.8rem 0 .8rem}}
p{{max-width:70ch}}
.meta{{font-family:var(--sans);font-size:.9rem;color:var(--tinta-2)}}
.cifras{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:1rem;margin:1.5rem 0;font-family:var(--sans)}}
.cifras div{{border-top:2px solid var(--regla);padding-top:.4rem}}
.cifras span{{display:block;font-size:.8rem;color:var(--tinta-2)}}
.cifras strong{{font-size:1.5rem;font-variant-numeric:tabular-nums}}
.cifras .alerta{{border-top-color:var(--riesgo)}}
.panel{{background:var(--papel);border:1px solid var(--regla);border-radius:12px;padding:1.2rem;overflow-x:auto}}
svg{{width:100%;height:auto;display:block;min-width:520px}}
svg .rej{{stroke:var(--regla);stroke-width:1}} svg .eje{{fill:var(--tinta-2);font:11px var(--sans)}}
svg .tit{{fill:var(--tinta-2);font:12px var(--sans)}} svg .lab{{fill:var(--tinta);font:600 12px var(--sans)}}
svg .ideal{{fill:var(--ok);font:italic 11px var(--sans)}}
svg .pt{{fill:var(--tinta-2)}} svg .pt.ef{{fill:var(--cobalto)}} svg .pt.nv{{fill:var(--papel);stroke:var(--riesgo);stroke-width:2}}
svg .techo{{stroke:var(--riesgo);stroke-width:1.5;stroke-dasharray:5 4}} svg .techo-t{{fill:var(--riesgo);font:italic 11px var(--sans)}} svg .nozona{{fill:var(--riesgo);opacity:.05}} svg .ic{{stroke:var(--tinta-2);stroke-width:1.5;opacity:.5}}
.tabla{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%;font-size:.9rem;font-variant-numeric:tabular-nums}}
th,td{{text-align:left;padding:.55rem .5rem;border-bottom:1px solid var(--regla);vertical-align:top}}
th{{font-weight:500;color:var(--tinta-2);font-size:.8rem}}
td small{{display:block;color:var(--tinta-2);font-size:.8rem;max-width:34ch}}
td i{{color:var(--tinta-2);font-style:normal;font-size:.82rem}}
tr.ef td:first-child{{border-left:3px solid var(--cobalto);padding-left:.6rem}}
ul{{max-width:70ch}} li{{margin-bottom:.4rem}}
footer{{margin-top:3rem;border-top:1px solid var(--regla);padding-top:.8rem;font-family:var(--sans);font-size:.8rem;color:var(--tinta-2)}}
</style></head><body><main>
<p class="meta">Banco de pruebas v1, generado el {datetime.now():%Y-%m-%d %H:%M}</p>
<h1>¿Qué estrategia de contención protege mejor las joyas de la corona?</h1>
<p>{len(info_topos)} topologías sintéticas de unos {nodos_prom:.0f} nodos y {enlaces_prom:.0f} enlaces, {sim["corridas_por_topologia"]} ataques simulados por topología. El ataque entra por {_e(", ".join(sim["capas_entrada"]))}; la contención se aplica en el paso {sim["paso_deteccion"]} de {sim["pasos_totales"]}. Todas las estrategias enfrentan exactamente los mismos ataques.</p>

<div class="cifras">
  <div class="alerta"><span>Joya ya perdida al detectar</span><strong>{pct_joya_det:.1f}%</strong></div>
  <div><span>Corridas contenibles</span><strong>{n_cont:,}</strong></div>
  <div><span>Prob. de observar un nodo infectado</span><strong>{100*sim["prob_observacion"]:.0f}%</strong></div>
  <div><span>Presupuesto de cortes (heurísticas)</span><strong>{est["presupuesto_cortes"]}</strong></div>
</div>
<p>En el {pct_joya_det:.1f}% de las corridas, el ataque ya había alcanzado una joya antes de la detección: ninguna contención puede evitarlo. Por eso la métrica principal se calcula solo sobre las corridas contenibles.</p>

<h2>Riesgo contra costo</h2>
<div class="panel">{_grafica(resumen, eficientes, techo)}</div>
<p class="meta">Barras verticales: intervalo de confianza del 95%. En azul, las estrategias eficientes: no superan el techo de costo de negocio ({techo:g}%), mejoran de forma estadísticamente significativa frente a no contener y ninguna otra es a la vez más barata y más protectora. Círculos huecos: estrategias no viables por costo. Eficientes en esta corrida: {lista_ef}.</p>

<h2>Resultados por estrategia</h2>
<div class="tabla"><table>
<thead><tr><th>Estrategia</th><th>Joya comprometida, contenibles (%)</th><th>Reducción vs. sin contención</th><th>Joya comprometida, total (%)</th><th>Nodos comprometidos</th><th>Costo de negocio (%)</th><th>Enlaces cortados</th></tr></thead>
<tbody>{"".join(filas)}</tbody></table></div>

<h2>Consistencia entre topologías</h2>
<p class="meta">Joya comprometida (%, todas las corridas) en cada topología. Si una estrategia solo gana en una topología, el resultado no es robusto.</p>
<div class="tabla"><table><thead><tr><th>Estrategia</th>{cab_topo}</tr></thead><tbody>{filas_topo}</tbody></table></div>

<h2>Supuestos de esta versión</h2>
<ul>
<li>Las topologías, probabilidades de propagación y valores de negocio son sintéticos: los resultados comparan estrategias entre sí dentro de este modelo, no predicen una red real.</li>
<li>El defensor solo ve una fracción de los nodos infectados; los no observados siguen propagando después de la contención.</li>
<li>Cortar un enlace lo desactiva por completo e inmediatamente; no hay reglas parciales ni demoras de aplicación.</li>
<li>Techo de costo de negocio aceptable: {techo:g}%. Una estrategia que lo supera se considera no viable aunque proteja más.</li>
<li>Las heurísticas con presupuesto cortan {est["presupuesto_cortes"]} enlaces; las estrategias basadas en modelo cortan lo que su lógica indique, y ese costo se refleja en la columna de negocio.</li>
</ul>
<footer>Semilla global {cfg["semilla_global"]}. {sum(f["n"] for f in resumen):,} simulaciones en {duracion:.1f} s. Datos crudos en corridas.csv y resumen.csv.</footer>
</main></body></html>"""
