# A6.4 localhost-only starter. Do not use this script for LAN/Internet deployment.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backend = Join-Path $root 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$database = Join-Path $backend 'greenhouse.db'
$compose = Join-Path $backend 'docker-compose.yml'

if (-not (Test-Path -LiteralPath $python)) { throw 'A64_BACKEND_VENV_MISSING' }
if (-not (Test-Path -LiteralPath $database)) { throw 'A64_MAIN_DATABASE_MISSING' }
if (-not (Test-Path -LiteralPath (Join-Path $backend '.env'))) { throw 'A64_BACKEND_ENV_MISSING' }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'A64_DOCKER_COMMAND_MISSING' }
$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $listener | Select-Object LocalPort,OwningProcess | Format-Table
    throw 'A64_PORT_8000_IN_USE: stop the old Uvicorn tab (Ctrl+C).'
}

# Explicit flags override inherited shell variables and protect the LOCAL demo.
$env:DATABASE_URL = 'sqlite:///./greenhouse.db'
$env:AUTH_ENFORCEMENT_ENABLED = '1'
$env:AUTH_COOKIE_SECURE = '0' # HTTP on 127.0.0.1 ONLY; HTTPS deployments must use 1.
$env:MQTT_ENABLED = '1'
$env:MQTT_URL = 'mqtt://localhost:1883'
$env:CORS_ORIGINS = 'http://localhost:5173,http://127.0.0.1:5173'

# Strict localhost: reject outdated or incomplete databases before startup.
# Never auto-create missing tables on the secure path.
$env:AUTO_CREATE_TABLES = '0'

$preflight = Join-Path $root 'ops\check_secure_db.py'

if (-not (Test-Path -LiteralPath $preflight -PathType Leaf)) {
    throw 'A672_PREFLIGHT_SCRIPT_MISSING'
}

& $python $preflight --db $database

if ($LASTEXITCODE -ne 0) {
    throw 'A672_SECURE_DB_PREFLIGHT_FAILED'
}

Write-Host 'A672_SECURE_DB_PREFLIGHT_PASS' -ForegroundColor Green

Write-Host 'A64_BACKEND_STRICT=1 (127.0.0.1:8000)' -ForegroundColor Green
Write-Host 'A64_DATABASE=backend/greenhouse.db; MQTT_ENABLED=1' -ForegroundColor Green
& docker compose -p backend -f $compose up -d
if ($LASTEXITCODE -ne 0) { throw 'A64_MQTT_BROKER_START_FAILED' }

Push-Location $backend
try {
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    if ($LASTEXITCODE -ne 0) { throw 'A64_BACKEND_EXITED_WITH_ERROR' }
}
finally { Pop-Location }
