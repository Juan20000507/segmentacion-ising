"""
Max-Cut ponderado de servidores con D-Wave Ocean (dimod).
Separa activos conectados en dos zonas maximizando el peso (criticidad)
de los enlaces cortados. Resuelve en Ising (nativo) y QUBO, y valida que coincidan.

Uso:  python maxcut_servidores.py [ruta_config.json]
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import dimod

RUTA_DEFECTO = Path(__file__).with_name("config_grafo.json")


# ---------------------------------------------------------------- config
def cargar_config(ruta: Path) -> dict:
    if not ruta.exists():
        sys.exit(f"[ERROR] No existe el archivo de configuracion: {ruta}")
    with ruta.open(encoding="utf-8") as f:
        cfg = json.load(f)
    requeridas = ("aristas", "zonas", "exact_solver_max_variables",
                  "annealing", "tolerancia_energia")
    faltantes = [k for k in requeridas if k not in cfg]
    if faltantes:
        sys.exit(f"[ERROR] Faltan claves en {ruta.name}: {', '.join(faltantes)}")
    aristas = cfg.get("aristas") or []
    if not aristas:
        sys.exit("[ERROR] La configuracion no contiene aristas.")
    for a in aristas:
        if a["origen"] == a["destino"]:
            sys.exit(f"[ERROR] Arista a si misma no permitida: {a['origen']}")
        if float(a["peso"]) <= 0:
            sys.exit(f"[ERROR] Peso no positivo en {a['origen']}-{a['destino']}: "
                     "Max-Cut requiere pesos > 0.")
    return cfg


# ------------------------------------------------------------- modelos
def construir_ising(aristas: list) -> tuple[dict, dict]:
    """E = sum J_ij*s_i*s_j, J = peso > 0 (antiferromagnetico). h = 0."""
    J = defaultdict(float)
    for a in aristas:
        J[(a["origen"], a["destino"])] += float(a["peso"])
    return {n: 0.0 for par in J for n in par}, dict(J)


def construir_qubo(aristas: list) -> tuple[dict, dict]:
    """Por arista: w*(-xi - xj + 2*xi*xj) -> -w si se corta, 0 si no."""
    lineal, cuadratico = defaultdict(float), defaultdict(float)
    for a in aristas:
        i, j, w = a["origen"], a["destino"], float(a["peso"])
        lineal[i] -= w
        lineal[j] -= w
        cuadratico[(i, j)] += 2.0 * w
    return dict(lineal), dict(cuadratico)


# ------------------------------------------------------------ analisis
def optimos(sampleset: dimod.SampleSet, tol: float) -> list:
    e_min = float(sampleset.first.energy)
    return [(dict(s), float(e)) for s, e in sampleset.data(["sample", "energy"])
            if abs(float(e) - e_min) <= tol]


def a_binario(muestra: dict) -> dict:
    return {k: (1 if v == 1 else 0) for k, v in muestra.items()}


def evaluar(muestra: dict, aristas: list) -> tuple[list, list]:
    cortadas = [a for a in aristas if muestra[a["origen"]] != muestra[a["destino"]]]
    residuales = [a for a in aristas if muestra[a["origen"]] == muestra[a["destino"]]]
    return cortadas, residuales


def canonicas(soluciones: list, nodos: list) -> list:
    """Elimina la simetria global (invertir todos los espines = misma particion)."""
    vistas, salida = set(), []
    for s, e in soluciones:
        clave = frozenset(frozenset(n for n in nodos if s[n] == v) for v in (1, -1))
        if clave not in vistas:
            vistas.add(clave)
            salida.append((s, e))
    return salida


# ------------------------------------------------------------- reporte
def reporte(soluciones: list, cfg: dict, nodos: list) -> None:
    etiquetas = cfg.get("nodos", {})
    zonas = cfg["zonas"]
    aristas = cfg["aristas"]
    total = sum(float(a["peso"]) for a in aristas)

    print("\n" + "=" * 70)
    print(" SEGMENTACION OPTIMA - REPORTE PARA COMITE DE SEGURIDAD")
    print("=" * 70)
    for k, (s, e) in enumerate(soluciones, 1):
        cortadas, residuales = evaluar(s, aristas)
        mitigado = sum(float(a["peso"]) for a in cortadas)
        print(f"\nSolucion {k}  (energia Ising {e:.2f})")
        for zona_spin, zona_nombre in ((1, zonas["spin_positivo"]),
                                       (-1, zonas["spin_negativo"])):
            miembros = [etiquetas.get(n, n) for n in nodos if s[n] == zona_spin]
            print(f"  {zona_nombre:<12}: {', '.join(miembros) or '(vacia)'}")
        print("  Enlaces segmentados (mitigados):")
        for a in sorted(cortadas, key=lambda x: -float(x["peso"])):
            print(f"    {a['origen']:>4} - {a['destino']:<4} peso {float(a['peso']):>6.1f}"
                  f"  {a.get('nota', '')}")
        print("  Riesgo residual (misma zona):")
        for a in sorted(residuales, key=lambda x: -float(x["peso"])) or []:
            print(f"    {a['origen']:>4} - {a['destino']:<4} peso {float(a['peso']):>6.1f}"
                  f"  {a.get('nota', '')}")
        if not residuales:
            print("    (ninguno)")
        print(f"  Criticidad mitigada: {mitigado:.1f} de {total:.1f} "
              f"({100 * mitigado / total:.1f}%)")


# ---------------------------------------------------------------- main
def main() -> None:
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else RUTA_DEFECTO
    cfg = cargar_config(ruta)
    aristas, tol = cfg["aristas"], float(cfg["tolerancia_energia"])
    nodos = sorted({a["origen"] for a in aristas} | {a["destino"] for a in aristas})
    print(f"[INFO] Configuracion: {ruta.name} | {len(nodos)} nodos, {len(aristas)} enlaces")

    if len(nodos) > cfg["exact_solver_max_variables"]:
        sys.exit(f"[ERROR] {len(nodos)} nodos excede el limite de ExactSolver "
                 f"({cfg['exact_solver_max_variables']}). Use annealing.")

    exacto = dimod.ExactSolver()

    # 1) Ising (formulacion principal)
    h, J = construir_ising(aristas)
    sol_ising = optimos(exacto.sample_ising(h, J), tol)

    # 2) QUBO (validacion cruzada)
    lq, cq = construir_qubo(aristas)
    bqm_qubo = dimod.BinaryQuadraticModel(lq, cq, 0.0, dimod.BINARY)
    sol_qubo = optimos(exacto.sample(bqm_qubo), tol)

    part_i = {tuple(a_binario(s)[n] for n in nodos) for s, _ in sol_ising}
    part_q = {tuple(s[n] for n in nodos) for s, _ in sol_qubo}
    assert part_i == part_q, "Ising y QUBO no coinciden en las particiones optimas"
    assert all(len(set(p)) > 1 for p in part_i), "Particion trivial detectada"
    print(f"[OK] Validacion cruzada Ising/QUBO: {len(part_i)} estados optimos coinciden")

    mostrar = sol_ising if cfg.get("mostrar_simetricas") else canonicas(sol_ising, nodos)
    reporte(mostrar, cfg, nodos)

    # 3) Recocido simulado (opcional)
    if cfg["annealing"]["habilitado"]:
        try:
            from dwave.samplers import SimulatedAnnealingSampler
        except ImportError:
            print("\n[INFO] dwave-samplers no instalado; se omite recocido simulado.")
            return
        sa = SimulatedAnnealingSampler().sample_ising(
            h, J, num_reads=cfg["annealing"]["num_reads"], seed=cfg["annealing"]["seed"])
        e_sa, e_opt = float(sa.first.energy), sol_ising[0][1]
        estado = "OK" if abs(e_sa - e_opt) <= tol else "SUBOPTIMO"
        print(f"\n[{estado}] Recocido simulado: energia {e_sa:.2f} (optimo exacto {e_opt:.2f})")


if __name__ == "__main__":
    main()
