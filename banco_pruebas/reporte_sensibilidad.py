"""Reporte HTML autocontenido del analisis de sensibilidad."""
import html
from datetime import datetime

from reporte import ETIQUETAS


def _e(x):
    return html.escape(str(x))


def _nombre(est):
    return ETIQUETAS.get(est, (est,))[0]


def _mapa(escenarios, pasos, visib, valor, clase, titulo, fmt="{:.1f}%"):
    """Mapa de calor: filas = paso de deteccion, columnas = visibilidad."""
    celda, L, T = 110, 118, 46
    W, H = L + celda * len(visib) + 10, T + celda * 0.62 * len(pasos) + 34
    alto = celda * 0.62
    idx = {(e["paso_deteccion"], e["prob_observacion"]): e for e in escenarios}
    vals = [valor(e) for e in escenarios]
    vmin, vmax = min(vals), max(vals)
    g = [f'<text x="{L + celda*len(visib)/2:.0f}" y="16" text-anchor="middle" class="tit">Visibilidad del defensor</text>']
    for j, v in enumerate(visib):
        g.append(f'<text x="{L + celda*j + celda/2:.0f}" y="{T-10}" text-anchor="middle" class="eje">{v:.0%}</text>')
    g.append(f'<text transform="translate(16,{T + alto*len(pasos)/2:.0f}) rotate(-90)" text-anchor="middle" class="tit">Paso de detección</text>')
    for i, p in enumerate(pasos):
        y = T + alto * i
        g.append(f'<text x="{L-12}" y="{y + alto/2 + 4:.0f}" text-anchor="end" class="eje">Paso {p}</text>')
        for j, v in enumerate(visib):
            e = idx[(p, v)]
            x_ = valor(e)
            op = 0.08 + 0.82 * ((x_ - vmin) / (vmax - vmin) if vmax > vmin else 0.5)
            tcol = "claro" if op > 0.55 else "osc"
            x = L + celda * j
            g.append(f'<rect x="{x+2}" y="{y+2:.0f}" width="{celda-4}" height="{alto-4:.0f}" rx="6" class="{clase}" fill-opacity="{op:.2f}"/>'
                     f'<text x="{x+celda/2:.0f}" y="{y+alto/2+6:.0f}" text-anchor="middle" class="val {tcol}">{fmt.format(x_)}</text>')
    g.append(f'<text x="{L}" y="{H-8:.0f}" class="nota-svg">Abajo: detección más tardía. Derecha: más visibilidad.</text>')
    return (f'<figure><figcaption>{_e(titulo)}</figcaption>'
            f'<svg viewBox="0 0 {W:.0f} {H:.0f}" role="img" aria-label="{_e(titulo)}">{"".join(g)}</svg></figure>')


def _barras(escenarios):
    W, L, R, fila = 720, 150, 20, 30
    H = 30 + fila * len(escenarios) + 16 * 3 + 30
    X = lambda v: L + v / 100 * (W - L - R)
    g, y, paso_ant = [], 24, None
    for v in range(0, 101, 25):
        g.append(f'<line x1="{X(v):.1f}" x2="{X(v):.1f}" y1="14" y2="{H-34}" class="rej"/>'
                 f'<text x="{X(v):.1f}" y="{H-20}" text-anchor="middle" class="eje">{v}%</text>')
    for e in escenarios:
        if paso_ant is not None and e["paso_deteccion"] != paso_ant:
            y += 16
        paso_ant = e["paso_deteccion"]
        a = e["pct_joya_det"]
        b = max(0.0, e["mejor"]["joya_comprometida"] - a)
        c = max(0.0, 100 - a - b)
        base = e["base"]["joya_comprometida"]
        g.append(f'<text x="{L-10}" y="{y+15}" text-anchor="end" class="eje">Paso {e["paso_deteccion"]}, visib. {e["prob_observacion"]:.0%}</text>')
        g.append(f'<rect x="{X(0):.1f}" y="{y}" width="{X(a)-X(0):.1f}" height="20" class="s-antes"><title>Pérdida antes de detectar: {a:.1f}%</title></rect>')
        g.append(f'<rect x="{X(a):.1f}" y="{y}" width="{X(a+b)-X(a):.1f}" height="20" class="s-despues"><title>Pérdida tras contener: {b:.1f}%</title></rect>')
        g.append(f'<rect x="{X(a+b):.1f}" y="{y}" width="{X(100)-X(a+b):.1f}" height="20" class="s-salvo"><title>Protegida: {c:.1f}%</title></rect>')
        g.append(f'<line x1="{X(base):.1f}" x2="{X(base):.1f}" y1="{y-3}" y2="{y+23}" class="s-base"/>')
        y += fila
    g.append(f'<text x="{W/2:.0f}" y="{H-4}" text-anchor="middle" class="tit">Porcentaje de ataques simulados</text>')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Descomposición de la pérdida de joyas por escenario">{"".join(g)}</svg>'


def _efectos(escenarios, pasos, visib):
    idx = {(e["paso_deteccion"], e["prob_observacion"]): e["mejor"]["joya_comprometida"] for e in escenarios}
    ef_vis = sum(idx[(p, visib[0])] - idx[(p, visib[-1])] for p in pasos) / len(pasos)
    ef_det = sum(idx[(pasos[-1], v)] - idx[(pasos[0], v)] for v in visib) / len(visib)
    vis_temprano = idx[(pasos[0], visib[0])] - idx[(pasos[0], visib[-1])]
    vis_tardio = idx[(pasos[-1], visib[0])] - idx[(pasos[-1], visib[-1])]
    return ef_vis, ef_det, vis_temprano, vis_tardio


def generar_html(cfg, escenarios, duracion):
    sens = cfg["sensibilidad"]
    techo = float(cfg["reporte"]["techo_costo_negocio_pct"])
    pasos = sorted(sens["paso_deteccion"])
    visib = sorted(sens["prob_observacion"])
    ef_vis, ef_det, vis_t, vis_r = _efectos(escenarios, pasos, visib)
    if abs(ef_det - ef_vis) < 2:
        titular = "Detectar antes y ver más pesan parecido, dentro de estos rangos."
    elif ef_det > ef_vis:
        titular = "Detectar antes pesa más que ver más, dentro de estos rangos."
    else:
        titular = "Ver más pesa más que detectar antes, dentro de estos rangos."
    if vis_t - vis_r > 2:
        titular_int, cola_int = "Los dos factores se potencian.", " Si el ataque ya llegó lejos, ver más ayuda menos."
    elif vis_r - vis_t > 2:
        titular_int, cola_int = "La visibilidad pesa más cuanto más tarde se detecta.", ""
    else:
        titular_int, cola_int = "Los dos factores actúan de forma casi independiente.", ""
    mejores = sorted({e["mejor"]["estrategia"] for e in escenarios})
    costo_max = max(e["mejor"]["costo_negocio_pct"] for e in escenarios)
    costo_min = min(e["mejor"]["costo_negocio_pct"] for e in escenarios)

    mapa_joya = _mapa(escenarios, pasos, visib, lambda e: e["mejor"]["joya_comprometida"], "c-riesgo",
                      "Joya perdida con la mejor estrategia viable (% de ataques)")
    mapa_costo = _mapa(escenarios, pasos, visib, lambda e: e["mejor"]["costo_negocio_pct"], "c-cobre",
                       "Costo de negocio de esa estrategia (%)")

    estrategias = [f["estrategia"] for f in escenarios[0]["resumen"]]
    seccion_v2 = ""
    if {"mincut", "corte_riesgo"} <= set(estrategias):
        def _f(e, est):
            return next(f for f in e["resumen"] if f["estrategia"] == est)
        mejora = lambda e: _f(e, "mincut")["joya_comprometida"] - _f(e, "corte_riesgo")["joya_comprometida"]
        costo_extra = lambda e: _f(e, "corte_riesgo")["costo_negocio_pct"] - _f(e, "mincut")["costo_negocio_pct"]
        m_v2 = _mapa(escenarios, pasos, visib, mejora, "c-ok", "Puntos de pérdida que evita el v2 frente al corte mínimo", fmt="{:+.1f}")
        m_c = _mapa(escenarios, pasos, visib, costo_extra, "c-cobre", "Costo de negocio adicional del v2 (puntos)", fmt="{:+.1f}")
        vals = [mejora(e) for e in escenarios]
        e_max = max(escenarios, key=mejora)
        seccion_v2 = (f'<h2>Modelo v2 frente al corte mínimo</h2>'
                      f'<p>El v2 evita entre {min(vals):.1f} y {max(vals):.1f} puntos de pérdida según el escenario. '
                      f'Donde más aporta es con detección en el paso {e_max["paso_deteccion"]} y visibilidad de '
                      f'{e_max["prob_observacion"]:.0%}.</p><div class="mapas">{m_v2}{m_c}</div>')
    cab = "".join(f"<th>{_e(_nombre(s))}</th>" for s in estrategias)
    cuerpo = []
    for e in escenarios:
        celdas = []
        for f in e["resumen"]:
            nv = f["costo_negocio_pct"] > techo
            clase = ' class="nv"' if nv else (' class="mejor"' if f["estrategia"] == e["mejor"]["estrategia"] else "")
            celdas.append(f'<td{clase}>{f["joya_comprometida"]:.1f}<small>{f["costo_negocio_pct"]:.1f}% costo</small></td>')
        cuerpo.append(f'<tr><th scope="row">Paso {e["paso_deteccion"]}<br>visib. {e["prob_observacion"]:.0%}</th>{"".join(celdas)}</tr>')

    sim = cfg["simulacion"]
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Análisis de sensibilidad: visibilidad y detección</title>
<style>
:root{{--fondo:#EDF0F3;--papel:#F8F9FA;--tinta:#17222C;--tinta-2:#4A5864;--regla:#C7CFD6;--cobre:#B5692F;--cobalto:#2C58A0;--riesgo:#A23B30;--riesgo-suave:#E3B4AE;--ok:#2F7A55;--ok-suave:#CFE3D8;
--sans:"Segoe UI",system-ui,-apple-system,sans-serif;--serif:Georgia,"Times New Roman",serif;box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--fondo:#121A21;--papel:#18222B;--tinta:#E4E9EE;--tinta-2:#A3B0BB;--regla:#2E3C48;--cobre:#D98A4E;--cobalto:#6E97DB;--riesgo:#E07466;--riesgo-suave:#5A2E2A;--ok:#5DB889;--ok-suave:#1F3A2C}}}}
:root[data-theme="dark"]{{--fondo:#121A21;--papel:#18222B;--tinta:#E4E9EE;--tinta-2:#A3B0BB;--regla:#2E3C48;--cobre:#D98A4E;--cobalto:#6E97DB;--riesgo:#E07466;--riesgo-suave:#5A2E2A;--ok:#5DB889;--ok-suave:#1F3A2C}}
*,*::before,*::after{{box-sizing:inherit}}
body{{margin:0;background:var(--fondo);color:var(--tinta);font-family:var(--serif);line-height:1.6}}
main{{max-width:1040px;margin:0 auto;padding:2.5rem 1.2rem 4rem}}
h1,h2,table,figcaption{{font-family:var(--sans)}}
h1{{font-size:clamp(1.7rem,4vw,2.5rem);line-height:1.1;margin:.3rem 0 .8rem;letter-spacing:-.02em}}
h2{{font-size:1.3rem;margin:2.8rem 0 .8rem}}
p,ul{{max-width:70ch}} li{{margin-bottom:.45rem}}
.meta{{font-family:var(--sans);font-size:.9rem;color:var(--tinta-2)}}
.lectura{{background:var(--papel);border-left:3px solid var(--cobalto);padding:1rem 1.3rem;margin:1.5rem 0;max-width:74ch}}
.lectura p:last-child{{margin-bottom:0}}
.mapas{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1.2rem}}
figure{{margin:0;background:var(--papel);border:1px solid var(--regla);border-radius:12px;padding:1rem}}
figcaption{{font-weight:600;font-size:.95rem;margin-bottom:.4rem}}
.panel{{background:var(--papel);border:1px solid var(--regla);border-radius:12px;padding:1.2rem;overflow-x:auto}}
svg{{width:100%;height:auto;display:block}}
.panel svg{{min-width:560px}}
svg .eje{{fill:var(--tinta-2);font:12px var(--sans)}} svg .tit{{fill:var(--tinta-2);font:12px var(--sans)}}
svg .nota-svg{{fill:var(--tinta-2);font:italic 10.5px var(--sans)}}
svg .val{{font:700 17px var(--sans)}} svg .val.osc{{fill:var(--tinta)}} svg .val.claro{{fill:#fff}}
svg .c-riesgo{{fill:var(--riesgo)}} svg .c-cobre{{fill:var(--cobre)}} svg .c-ok{{fill:var(--ok)}}
svg .rej{{stroke:var(--regla);stroke-width:1}}
svg .s-antes{{fill:var(--riesgo)}} svg .s-despues{{fill:var(--riesgo-suave)}} svg .s-salvo{{fill:var(--ok-suave)}}
svg .s-base{{stroke:var(--tinta);stroke-width:2.5}}
.leyenda{{display:flex;flex-wrap:wrap;gap:1.2rem;font-family:var(--sans);font-size:.84rem;color:var(--tinta-2);margin-top:.6rem}}
.leyenda i{{display:inline-block;width:14px;height:14px;border-radius:3px;vertical-align:-2px;margin-right:.35rem}}
.tabla{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%;font-size:.86rem;font-variant-numeric:tabular-nums}}
th,td{{text-align:left;padding:.5rem .45rem;border-bottom:1px solid var(--regla);vertical-align:top}}
thead th{{font-weight:500;color:var(--tinta-2);font-size:.78rem}}
tbody th{{font-weight:500;white-space:nowrap}}
td small{{display:block;color:var(--tinta-2);font-size:.74rem}}
td.mejor{{background:rgba(44,88,160,.12);font-weight:700}}
td.nv{{color:var(--tinta-2);text-decoration:line-through;text-decoration-color:var(--riesgo)}}
footer{{margin-top:3rem;border-top:1px solid var(--regla);padding-top:.8rem;font-family:var(--sans);font-size:.8rem;color:var(--tinta-2)}}
</style></head><body><main>
<p class="meta">Análisis de sensibilidad, generado el {datetime.now():%Y-%m-%d %H:%M}</p>
<h1>¿Qué pesa más: ver más o detectar antes?</h1>
<p>El banco de pruebas se repitió en {len(escenarios)} escenarios que combinan la visibilidad del defensor (probabilidad de observar cada nodo infectado) con el momento de la detección. Topologías y ataques son idénticos en todos los escenarios; solo cambian esos dos parámetros. Techo de costo de negocio aceptable: {techo:g}%.</p>

<div class="lectura">
<p><b>{titular}</b> Pasar de detectar en el paso {pasos[-1]} al paso {pasos[0]} reduce la pérdida de joyas en {ef_det:.1f} puntos en promedio; pasar de {visib[0]:.0%} a {visib[-1]:.0%} de visibilidad la reduce en {ef_vis:.1f} puntos.</p>
<p><b>{titular_int}</b> La visibilidad vale {vis_t:.1f} puntos cuando se detecta en el paso {pasos[0]} y {vis_r:.1f} cuando se detecta en el paso {pasos[-1]}.{cola_int}</p>
<p><b>Ver más cuesta más.</b> Al observar más nodos infectados hay más que aislar: el costo de negocio de la mejor estrategia va de {costo_min:.1f}% a {costo_max:.1f}% entre escenarios. Mejor estrategia viable en todos los escenarios: {_e(", ".join(_nombre(m) for m in mejores))}.</p>
</div>

<div class="mapas">{mapa_joya}{mapa_costo}</div>

{seccion_v2}

<h2>De dónde viene la pérdida</h2>
<p>Cada barra divide los ataques en tres partes: los que ya habían alcanzado una joya al detectar (ninguna contención los evita), los que la alcanzan después de contener, por nodos infectados que el defensor no vio, y los que quedan protegidos. La línea negra marca la pérdida sin contención.</p>
<div class="panel">{_barras(escenarios)}
<div class="leyenda"><span><i style="background:var(--riesgo)"></i>Pérdida antes de detectar</span><span><i style="background:var(--riesgo-suave)"></i>Pérdida tras contener</span><span><i style="background:var(--ok-suave)"></i>Protegida</span><span><i style="background:var(--tinta);width:3px"></i>Sin contención</span></div>
</div>

<h2>Todas las estrategias en todos los escenarios</h2>
<p class="meta">Joya comprometida (% de todos los ataques) y costo de negocio. Resaltada: la mejor estrategia viable del escenario. Tachadas: no viables por superar el techo de costo.</p>
<div class="tabla"><table><thead><tr><th>Escenario</th>{cab}</tr></thead><tbody>{"".join(cuerpo)}</tbody></table></div>

<h2>Cómo leer estos resultados</h2>
<ul>
<li>Las comparaciones entre factores dependen de los rangos elegidos: {", ".join(f"{v:.0%}" for v in visib)} de visibilidad y pasos {", ".join(str(p) for p in pasos)} de {sim["pasos_totales"]}. Otros rangos pueden cambiar cuál pesa más.</li>
<li>Un "paso" es una unidad abstracta de propagación, no un tiempo real. Traducirlo a minutos u horas requiere calibrar con datos de incidentes.</li>
<li>Las topologías y probabilidades siguen siendo sintéticas; el valor está en la comparación relativa, no en las cifras absolutas.</li>
</ul>
<footer>Semilla global {cfg["semilla_global"]}. {sens["corridas_por_topologia"]} ataques por topología, {cfg["topologias"]["cantidad"]} topologías por escenario. {len(escenarios)} escenarios en {duracion:.0f} s. Datos en sensibilidad.csv.</footer>
</main></body></html>"""
