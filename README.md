# Segmentación Ising: contención de incidentes como problema de optimización

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22906001.svg)](https://doi.org/10.5281/zenodo.22906001)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Banco de pruebas reproducible y modelos de optimización para decidir **qué segmentos de red aislar durante un incidente de seguridad**, con comparación sistemática entre solvers clásicos y formulaciones QUBO/Ising.

Este repositorio contiene el código que genera todos los resultados del artículo:

> Herrera C., J. C. (2026). *Preparación cuántica aplicada a la contención de incidentes: de Max-Cut a un solver híbrido clásico–QUBO*. Preimpresión v1.1. Ver `docs/paper_v1.1.html`. DOI: [10.5281/zenodo.22906001](https://doi.org/10.5281/zenodo.22906001)

## Qué hay aquí

| Carpeta | Contenido |
|---|---|
| `banco_pruebas/` | Generador de topologías, simulador de propagación, estrategias de contención, análisis de sensibilidad, comparación de solvers y generadores de reportes |
| `docs/` | El artículo completo, con figuras, tablas y glosario |
| `ejemplos/` | Configuraciones de ejemplo |
| raíz | Microservicio FastAPI que expone el modelo, y lanzadores `.bat` para Windows |

## Resumen de los resultados

Cinco experimentos, todos ejecutados de forma independiente en Linux y Windows:

1. **Max-Cut ponderado (v1)**: protege, pero interrumpe el 92,1 % del negocio. Inviable.
2. **Sensibilidad**: el techo de protección lo fijan la rapidez de detección y la visibilidad, no el optimizador.
3. **Corte con riesgo inferido (v2)**: reduce la pérdida de activos críticos un 38 % frente al corte mínimo, con el mismo costo que una heurística equivalente.
4. **Cuarentena limitada (v3)**: el QUBO con recocido no supera a un control clásico elemental (Lagrange + búsqueda local), que alcanza el óptimo en el 100 % de las instancias con límites de hasta 5 nodos.
5. **k zonas y escalamiento (v4)**: sin estructura de corte de grafo y hasta 1.120 activos, el QUBO queda por detrás en las 40 instancias y se degrada **antes** que el método exacto.

## Instalación

Requiere Python 3.9 a 3.13.

```bash
python -m venv .venv_maxcut
source .venv_maxcut/bin/activate        # Windows: .venv_maxcut\Scripts\activate
pip install -r requirements.txt
```

En Windows, los archivos `.bat` de la raíz hacen todo lo anterior automáticamente: crean el entorno, instalan dependencias, ejecutan y abren el reporte.

## Reproducir los experimentos

Todos los parámetros están en `banco_pruebas/config_banco.json`. Con la semilla global `2026` los resultados son reproducibles cifra por cifra, salvo los solvers estocásticos, que pueden variar mínimamente entre plataformas.

```bash
python banco_pruebas/banco.py              # ~6 min  -> reporte_banco.html
python banco_pruebas/sensibilidad.py       # ~10 min -> reporte_sensibilidad.html
python banco_pruebas/comparar_solvers.py   # ~6 min  -> reporte_solvers.html
python banco_pruebas/comparar_v4.py        # ~8 min  -> solvers_v4.csv
python banco_pruebas/comparar_escala.py    # ~12 min -> escala.csv
```

Los resultados se escriben en `banco_pruebas/resultados/` (excluida del control de versiones).

## Microservicio

```bash
python servidor.py     # escucha en 127.0.0.1:8765, abre la documentación interactiva
```

`POST /api/v1/mitigar` recibe la topología con la criticidad de cada enlace y devuelve la segmentación propuesta, el riesgo residual y el costo de negocio. El servicio escucha solo en local; para exponerlo, defina la variable de entorno `MAXCUT_API_KEY` y envíe la cabecera `X-API-Key`.

## Advertencias

- Las topologías, probabilidades de propagación y valores de negocio son **sintéticos**. Los resultados comparan estrategias entre sí dentro de ese modelo; no predicen el comportamiento de una red real.
- Este código produce **propuestas de contención para revisión humana**, no acciones automáticas. Aislar segmentos de una red en producción sin aprobación puede interrumpir servicios críticos.
- No se ejecutó ningún experimento en hardware cuántico. Los resultados sobre QUBO se obtuvieron con recocido simulado clásico.

## Licencia

Código bajo licencia MIT (ver `LICENSE`). El artículo en `docs/` se distribuye bajo CC BY 4.0.
