@echo off
setlocal
rem La ruta del script permite iniciar desde cualquier carpeta y admite espacios.
set "TECHGEAR_PYTHON=%~dp0techgear_web\.venv\Scripts\python.exe"
if not exist "%TECHGEAR_PYTHON%" (
    echo Falta el entorno virtual de techgear_web. Consulta README.md.
    exit /b 1
)
"%TECHGEAR_PYTHON%" "%~dp0scripts\run_local.py" %*
set "TECHGEAR_EXIT=%ERRORLEVEL%"
if not "%TECHGEAR_EXIT%"=="0" (
    echo.
    echo El inicio fallo. Revisa el mensaje anterior.
)
exit /b %TECHGEAR_EXIT%