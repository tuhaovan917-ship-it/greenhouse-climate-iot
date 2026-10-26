# A6.4 localhost-only starter. The frontend never stores the session cookie value.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dashboard = Join-Path $root 'dashboard'
if (-not (Test-Path -LiteralPath (Join-Path $dashboard 'node_modules'))) { throw 'A64_DASHBOARD_DEPENDENCIES_MISSING: run npm ci in dashboard.' }
if (-not (Test-Path -LiteralPath (Join-Path $dashboard '.env'))) { throw 'A64_DASHBOARD_ENV_MISSING' }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'A64_NPM_COMMAND_MISSING' }
$listener = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $listener | Select-Object LocalPort,OwningProcess | Format-Table
    throw 'A64_PORT_5173_IN_USE: stop the old Vite tab (Ctrl+C).'
}

# Explicit flags override the shell and the Vite .env file.
$env:VITE_AUTH_GATE_ENABLED = '1'
$env:VITE_API_BASE_URL = 'http://localhost:8000'
$env:VITE_WS_URL = 'ws://localhost:8000/ws'
$env:VITE_DEVICE_ID = 'greenhouse-01'
$env:VITE_API_KEY = '' # Never ship credentials in public VITE_* variables.

try {
    $health = Invoke-RestMethod -Uri 'http://localhost:8000/api/health' -TimeoutSec 5 -ErrorAction Stop
    if ($health.status -ne 'ok' -or $health.db -ne 'ok') { throw 'Backend health reports a problem.' }
    if (-not $health.mqttConnected) { Write-Warning 'Backend is up but MQTT is not connected. Check Docker before Wokwi.' }
}
catch { throw ('A64_BACKEND_NOT_READY: ' + $_.Exception.Message) }

Write-Host 'A64_DASHBOARD_AUTH_GATE=1 (http://localhost:5173/)' -ForegroundColor Green
Push-Location $dashboard
try {
    & npm.cmd run dev -- --host localhost --port 5173 --strictPort
    if ($LASTEXITCODE -ne 0) { throw 'A64_DASHBOARD_EXITED_WITH_ERROR' }
}
finally { Pop-Location }
