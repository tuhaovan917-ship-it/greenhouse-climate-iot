<#
.SYNOPSIS
Chay toan bo stack demo tren may (khong can Docker).

.DESCRIPTION
Dung khi may khong co Docker Desktop: broker MQTT chay bang amqtt (dev
dependency), Backend dung uvicorn, Dashboard dung Vite dev server, va mot
thiet bi ao dong vai ESP32.

Neu may co Docker, lam theo README.md muc 4.2 (Mosquitto that) va bo
tham so -do thiet bi ao, thay bang Wokwi.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\backend\scripts\run_local_demo.ps1
#>
param(
    [int]$BrokerPort = 1883,
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173,
    [switch]$NoMockDevice
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$backend = Join-Path $root "backend"
$python = Join-Path $backend ".venv\Scripts\python.exe"
$logs = Join-Path $root ".runlogs"

if (-not (Test-Path $python)) {
    throw "Chua co moi truong ao. Chay: py -3.11 -m venv .\backend\.venv; & .\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt -r .\database\requirements.txt"
}

New-Item -ItemType Directory -Path $logs -Force | Out-Null

function Stop-Stack {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like "*_broker_dev.py*" -or $_.CommandLine -like "*demo_esp32_mock.py*" -or $_.CommandLine -like "*uvicorn*app.main*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
        Where-Object { $_.CommandLine -like "*vite*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

Stop-Stack
Start-Sleep -Seconds 1

Write-Host "[1/4] MQTT broker (amqtt) tren port $BrokerPort" -ForegroundColor Cyan
Start-Process -FilePath $python -ArgumentList (Join-Path $PSScriptRoot "_broker_dev.py"), $BrokerPort `
    -WorkingDirectory $backend -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "broker.log") -RedirectStandardError (Join-Path $logs "broker.err")

Start-Sleep -Seconds 4
Write-Host "[2/4] Backend (FastAPI) tren port $ApiPort" -ForegroundColor Cyan
$env:MQTT_URL = "mqtt://127.0.0.1:$BrokerPort"
Start-Process -FilePath $python -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $ApiPort `
    -WorkingDirectory $backend -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "backend.log") -RedirectStandardError (Join-Path $logs "backend.err")

Start-Sleep -Seconds 6
Write-Host "[3/4] Dashboard (Vite) tren port $WebPort" -ForegroundColor Cyan
$env:VITE_API_BASE_URL = "http://127.0.0.1:$ApiPort"
$env:VITE_WS_URL = "ws://127.0.0.1:$ApiPort/ws"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "npm.cmd run dev -- --host 127.0.0.1 --port $WebPort" `
    -WorkingDirectory (Join-Path $root "dashboard") -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "vite.log") -RedirectStandardError (Join-Path $logs "vite.err")

if (-not $NoMockDevice) {
    Start-Sleep -Seconds 6
    Write-Host "[4/4] Thiet bi ao (dong vai ESP32)" -ForegroundColor Cyan
    Start-Process -FilePath $python -ArgumentList "demo_esp32_mock.py", "--broker", "127.0.0.1", "--port", $BrokerPort, "--period", "2" `
        -WorkingDirectory $backend -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "mock.log") -RedirectStandardError (Join-Path $logs "mock.err")
} else {
    Write-Host "[4/4] Bo qua thiet bi ao (dung Wokwi)" -ForegroundColor Yellow
}

Start-Sleep -Seconds 8
Write-Host ""
Write-Host "  Dashboard : http://127.0.0.1:$WebPort" -ForegroundColor Green
Write-Host "  Swagger  : http://127.0.0.1:$ApiPort/docs" -ForegroundColor Green
Write-Host "  Health   : http://127.0.0.1:$ApiPort/api/health" -ForegroundColor Green
Write-Host "  Logs     : $logs" -ForegroundColor DarkGray
Write-Host ""
try {
    (Invoke-RestMethod "http://127.0.0.1:$ApiPort/api/health" -TimeoutSec 10) | ConvertTo-Json -Compress
} catch {
    Write-Warning "Backend chua san sang, xem $logs\backend.err"
}
