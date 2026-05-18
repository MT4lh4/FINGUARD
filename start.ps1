Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  FinGuard AI - Baslatiliyor (PowerShell)..." -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $PSScriptRoot

if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "[HATA] venv bulunamadi!" -ForegroundColor Red
    Pause
    exit
}

Write-Host "[BILGI] FastAPI sunucusu baslatiliyor... (localhost:8000)" -ForegroundColor Green
Start-Process cmd -ArgumentList "/k venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000"

Start-Sleep -Seconds 3

Write-Host "[BILGI] Tarayici aciliyor..." -ForegroundColor Green
Start-Process "http://127.0.0.1:8000/"

Write-Host "`nUygulamayi kapatmak icin acilan siyah pencereyi kapatin." -ForegroundColor Yellow
Start-Sleep -Seconds 5
exit
