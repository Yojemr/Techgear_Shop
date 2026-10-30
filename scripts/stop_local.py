"""Cierra servidores de este proyecto sin terminar otros procesos de Python."""

import argparse
import json
import os
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Se consulta identidad, ruta y parentesco. La salida no incluye líneas de comando
# ni variables privadas. No se cambian permisos ni la política de PowerShell.
STOP_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($env:TECHGEAR_STOP_ROOT).TrimEnd(
    [IO.Path]::DirectorySeparatorChar
) + [IO.Path]::DirectorySeparatorChar
$all = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -in @('python.exe', 'pythonw.exe', 'uvicorn.exe')
})
$roots = @($all | Where-Object {
    $owned = ($_.ExecutablePath -and $_.ExecutablePath.StartsWith(
        $root, [StringComparison]::OrdinalIgnoreCase
    )) -or ($_.CommandLine -and $_.CommandLine.IndexOf(
        $root, [StringComparison]::OrdinalIgnoreCase
    ) -ge 0)
    # No incluye create-admin, pruebas, otros scripts ni terminales de VS Code.
    $server = $_.CommandLine -match '(?i)\bmanage\.py"?\s+runserver\b' -or
        $_.CommandLine -match '(?i)\buvicorn(?:\.exe)?"?\s+app\.main:app\b' -or
        $_.CommandLine -match '(?i)\brun_local\.py(?:"|\s|$)'
    $owned -and $server
})
$targets = @{}
foreach ($item in $roots) { $targets[[int]$item.ProcessId] = $item }
do {
    $added = $false
    foreach ($item in $all) {
        if (-not $targets.ContainsKey([int]$item.ProcessId) -and
            $targets.ContainsKey([int]$item.ParentProcessId)) {
            $targets[[int]$item.ProcessId] = $item
            $added = $true
        }
    }
} while ($added)

$stopped = 0
$failed = 0
if ($env:TECHGEAR_STOP_CHECK -ne '1') {
    $supervisors = @($roots | Where-Object {
        $_.CommandLine -match '(?i)\brun_local\.py(?:"|\s|$)'
    })
    if ($supervisors.Count -gt 0) {
        # El lanzador actual recibe la solicitud y ejecuta su cierre normal.
        $folder = Join-Path $env:TECHGEAR_STOP_ROOT '.local'
        [IO.Directory]::CreateDirectory($folder) | Out-Null
        [IO.File]::WriteAllText((Join-Path $folder 'stop.request'), 'stop')
        for ($attempt = 0; $attempt -lt 32; $attempt++) {
            $alive = @($supervisors | Where-Object {
                $current = Get-CimInstance Win32_Process -Filter "ProcessId = $($_.ProcessId)"
                $current -and $current.CreationDate -eq $_.CreationDate
            })
            if ($alive.Count -eq 0) { break }
            Start-Sleep -Milliseconds 250
        }
    }
    # También cubre servidores iniciados manualmente y lanzadores anteriores.
    # Solo detiene los PID identificados, nunca árboles de VS Code ni del navegador.
    $ordered = @($roots) + @($targets.Values | Where-Object {
        $_.ProcessId -notin $roots.ProcessId
    })
    foreach ($item in $ordered) {
        $current = Get-CimInstance Win32_Process -Filter "ProcessId = $($item.ProcessId)"
        if ($current -and $current.CreationDate -eq $item.CreationDate) {
            try { Stop-Process -Id $item.ProcessId -Force -ErrorAction Stop }
            catch { $failed++ }
        }
    }
    foreach ($item in $targets.Values) {
        $current = Get-CimInstance Win32_Process -Filter "ProcessId = $($item.ProcessId)"
        if (-not $current -or $current.CreationDate -ne $item.CreationDate) { $stopped++ }
    }
}
[PSCustomObject]@{
    detected = $targets.Count
    stopped = $stopped
    failed = $failed
} | ConvertTo-Json -Compress
"""


def occupied_ports():
    """Informa puertos ocupados sin usarlos como autorización para matar procesos."""
    ports = []
    for port in (8000, 8001):
        with socket.socket() as connection:
            connection.settimeout(0.3)
            if connection.connect_ex(("127.0.0.1", port)) == 0:
                ports.append(port)
    return ports


def main():
    parser = argparse.ArgumentParser(description="Cierra los servidores locales de Techgear.")
    parser.add_argument("--check", action="store_true", help="Detecta servidores sin cerrarlos.")
    args = parser.parse_args()
    if os.name != "nt":
        print("Este comando de cierre corresponde a Windows.")
        return 1
    env = os.environ.copy()
    env["TECHGEAR_STOP_ROOT"] = str(ROOT)
    env["TECHGEAR_STOP_CHECK"] = "1" if args.check else "0"
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", STOP_SCRIPT],
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=25,
        )
        report = json.loads(result.stdout)
    except OSError, subprocess.SubprocessError, ValueError:
        print("No fue posible comprobar o cerrar los servidores de Techgear.")
        return 1
    if args.check:
        print(f"Procesos de servidores Techgear detectados: {report['detected']}.")
        return 0
    print(f"Procesos de servidores Techgear detenidos: {report['stopped']}.")
    ports = occupied_ports()
    if report["failed"] or report["stopped"] != report["detected"]:
        print("No se pudieron cerrar todos los procesos identificados.")
        return 1
    if ports:
        print("Siguen ocupados los puertos: " + ", ".join(map(str, ports)) + ".")
        print("Los procesos que no se identificaron como Techgear se conservaron.")
        return 1
    print("API y front detenidos. Puertos 8000 y 8001 libres.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
