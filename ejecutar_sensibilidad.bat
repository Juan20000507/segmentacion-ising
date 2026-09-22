@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
echo ============================================
echo   Analisis de sensibilidad - 9 escenarios
echo   Modo aislado (no interfiere con otros proyectos)
echo ============================================

rem --- Aislamiento: variables solo viven en esta ventana (setlocal) ---
set "PYTHONNOUSERSITE=1"
set "PIP_REQUIRE_VIRTUALENV=true"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "OMP_NUM_THREADS=1"
set "VENV=.venv_maxcut"

rem --- [0/4] Verificar que la carpeta no este dentro de otro proyecto ---
echo [0/4] Verificando ubicacion...
for %%M in (docker-compose.yml package.json pyproject.toml .venv venv requirements.txt) do (
  if exist "..\%%M" (
    echo [ERROR] La carpeta padre contiene "%%M": parece ser otro proyecto.
    echo         Mueve la carpeta maxcut a una ubicacion independiente, p.ej. C:\Proyectos\maxcut
    pause & exit /b 1
  )
)

rem --- [1/4] Seleccionar Python compatible (3.9 - 3.13) ---
echo [1/4] Buscando Python compatible...
set "PYBASE="
for %%V in (3.12 3.11 3.13 3.10) do (
  if not defined PYBASE (
    py -%%V -c "import sys" >nul 2>&1 && set "PYBASE=py -%%V"
  )
)
if not defined PYBASE (
  python -c "import sys; sys.exit(0 if (3,9)<=sys.version_info[:2]<=(3,13) else 1)" >nul 2>&1 && set "PYBASE=python"
)
if not defined PYBASE (
  echo [ERROR] No se encontro Python 3.9-3.13. Instala Python 3.12 y reintenta.
  pause & exit /b 1
)
echo       Usando: !PYBASE!

rem --- [2/4] Entorno virtual propio ---
if not exist "%VENV%\Scripts\python.exe" (
  echo [2/4] Creando entorno virtual %VENV%...
  !PYBASE! -m venv "%VENV%" || (echo [ERROR] No se pudo crear %VENV% & pause & exit /b 1)
) else (echo [2/4] Entorno virtual %VENV% existente.)
set "VPY=%CD%\%VENV%\Scripts\python.exe"

rem --- [3/4] Dependencias (solo dentro del venv) ---
echo [3/4] Instalando dependencias en %VENV%...
"%VPY%" -m pip install -r requirements.txt -q || (echo [ERROR] Fallo la instalacion. & pause & exit /b 1)

rem --- [4/4] Ejecutar con prioridad baja para no competir por CPU ---
echo [4/4] Ejecutando sensibilidad (prioridad baja, ~8-10 min)...
start "" /low /wait /b "%VPY%" banco_pruebas\sensibilidad.py %*
if errorlevel 1 (echo [ERROR] La ejecucion fallo.) else (
  echo [OK] Ejecucion completada.
  if exist "banco_pruebas\resultados\reporte_sensibilidad.html" start "" "banco_pruebas\resultados\reporte_sensibilidad.html"
)
pause
endlocal
