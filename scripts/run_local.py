"""Inicia FastAPI y Django en loopback y administra solo sus propios procesos."""

import argparse
import os
import signal
import socket
import subprocess
import threading
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parent.parent
STOP_FILE = ROOT / ".local" / "stop.request"
WEB_URL = "http://127.0.0.1:8000/"
API_URL = "http://127.0.0.1:8001"
PYTHONS = {
    name: ROOT / name / ".venv" / "Scripts" / "python.exe"
    for name in ("techgear_api", "techgear_web")
}


def check_setup():
    """Valida requisitos sin instalar paquetes ni modificar la base de datos."""
    modules = {
        "techgear_api": "import uvicorn, fastapi, pymongo, dotenv",
        "techgear_web": "import django, django_mongodb_backend, httpx, dotenv",
    }
    for name, python in PYTHONS.items():
        if not python.is_file():
            raise RuntimeError(f"Falta el entorno virtual de {name}. Consulta README.md.")
        # Las aplicaciones leen sus propios archivos .env; el lanzador no los imprime.
        if not (ROOT / name / ".env").is_file():
            raise RuntimeError(f"Falta {name}/.env. Configuralo desde .env.example.")
        result = subprocess.run(
            [str(python), "-c", modules[name]],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"Faltan dependencias en {name}. Consulta README.md.")

    # No reutiliza ni detiene servidores ajenos que ya ocupen estos puertos.
    for port in (8000, 8001):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            if os.name == "nt":
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                listener.bind(("127.0.0.1", port))
            except OSError:
                raise RuntimeError(
                    f"El puerto {port} esta ocupado. Cierra su servidor antes de iniciar."
                ) from None


def is_ready(url):
    """Consulta solo loopback, sin proxies del sistema ni datos de autenticacion."""
    try:
        with build_opener(ProxyHandler({})).open(url, timeout=1) as response:
            return response.status == 200
    except URLError, TimeoutError, OSError:
        return False


def stop_services(processes):
    """Cierra los grupos creados por este lanzador, incluidos los recargadores."""
    for process in reversed(processes):
        if process.poll() is not None:
            continue
        try:
            if os.name == "nt":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                process.terminate()
        except OSError:
            pass
    deadline = time.monotonic() + 5
    for process in reversed(processes):
        try:
            process.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                # El PID procede exclusivamente de Popen en esta ejecucion.
                subprocess.run(
                    ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                process.kill()
            process.wait(timeout=5)


def run_services(stop_requested, *, open_browser=True):
    """Mantiene ambos servicios en una consola hasta recibir la orden de cierre."""
    # Una solicitud anterior no debe detener una nueva ejecución.
    STOP_FILE.parent.mkdir(exist_ok=True)
    STOP_FILE.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    # Solo los procesos locales reciben estos valores; no se altera ningun .env.
    environment["DJANGO_DEBUG"] = "True"
    environment["TECHGEAR_API_URL"] = API_URL
    commands = [
        (
            "API",
            [
                str(PYTHONS["techgear_api"]),
                "-m",
                "uvicorn",
                "app.main:app",
                "--app-dir",
                "techgear_api",
                "--host",
                "127.0.0.1",
                "--port",
                "8001",
                "--reload",
            ],
        ),
        (
            "Front",
            [
                str(PYTHONS["techgear_web"]),
                "techgear_web/manage.py",
                "runserver",
                "127.0.0.1:8000",
            ],
        ),
    ]
    processes = []
    try:
        for label, command in commands:
            processes.append(
                subprocess.Popen(
                    command,
                    cwd=ROOT,
                    env=environment,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
                )
            )
            print(f"{label}: iniciando...", flush=True)
        deadline = time.monotonic() + 45
        while not stop_requested.is_set() and not STOP_FILE.exists():
            for (label, _), process in zip(commands, processes, strict=True):
                if process.poll() is not None:
                    raise RuntimeError(f"{label} se detuvo. Revisa el error en esta consola.")
            if is_ready(API_URL + "/") and is_ready(WEB_URL + "salud/"):
                print(f"\nTienda: {WEB_URL}\nSwagger: {API_URL}/docs", flush=True)
                print("Ctrl+C detiene los dos servicios.\n", flush=True)
                if open_browser:
                    webbrowser.open(WEB_URL)
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Los servidores no respondieron. Revisa esta consola.")
            stop_requested.wait(0.5)
        while not stop_requested.wait(0.5):
            if STOP_FILE.exists():
                break
            for (label, _), process in zip(commands, processes, strict=True):
                if process.poll() is not None:
                    raise RuntimeError(f"{label} se detuvo. Revisa el error en esta consola.")
        return 0
    finally:
        stop_services(processes)
        print("Servicios del lanzador detenidos.", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Arranca la tienda local de Techgear.")
    parser.add_argument("--check", action="store_true", help="Solo verifica entornos y puertos.")
    parser.add_argument("--no-browser", action="store_true", help="No abre el navegador.")
    options = parser.parse_args()
    stop_requested = threading.Event()

    # Windows usa SIGBREAK al cerrar un grupo; Ctrl+C en la consola utiliza SIGINT.
    def request_stop(_signal, _frame):
        stop_requested.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, request_stop)
    try:
        check_setup()
        if options.check:
            print("Entornos, dependencias, archivos .env y puertos verificados.")
            return 0
        return run_services(stop_requested, open_browser=not options.no_browser)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"No fue posible iniciar Techgear: {error}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
