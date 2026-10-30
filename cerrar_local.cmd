@echo off
setlocal
rem Usa rutas absolutas para aceptar espacios y ejecutarse desde cualquier carpeta.
set "TECHGEAR_PYTHON=%~dp0techgear_web\.venv\Scripts\python.exe"
if not exist "%TECHGEAR_PYTHON%" (
    echo Falta el entorno virtual de techgear_web.
    exit /b 1
)
"%TECHGEAR_PYTHON%" "%~dp0scripts\stop_local.py" %*
exit /b %ERRORLEVEL%