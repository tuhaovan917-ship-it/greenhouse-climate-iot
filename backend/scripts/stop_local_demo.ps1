<#
.SYNOPSIS
Dung toan bo stack demo chay nen (broker, Backend, Dashboard, thiet bi ao).

.EXAMPLE
powershell -ExecutionPolicy Bypass -File .\backend\scripts\stop_local_demo.ps1
#>
$ErrorActionPreference = "SilentlyContinue"

Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object {
        $_.CommandLine -like "*_broker_dev.py*" -or
        $_.CommandLine -like "*demo_esp32_mock.py*" -or
        $_.CommandLine -like "*uvicorn*app.main*"
    } |
    ForEach-Object {
        Write-Host "Dung PID $($_.ProcessId): $($_.CommandLine.Substring(0, [Math]::Min(80, $_.CommandLine.Length)))"
        Stop-Process -Id $_.ProcessId -Force
    }

Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
    Where-Object { $_.CommandLine -like "*vite*" } |
    ForEach-Object {
        Write-Host "Dung PID $($_.ProcessId) (vite)"
        Stop-Process -Id $_.ProcessId -Force
    }

Write-Host "Da dung stack." -ForegroundColor Green
