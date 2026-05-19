$ErrorActionPreference = "Stop"

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  FinGuard AI - Baslatiliyor (PowerShell)..." -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

# Proje dizinine git ($PSScriptRoot built-in'dir, ezme)
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Definition)

# venv kontrolu
if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "[HATA] venv bulunamadi!" -ForegroundColor Red
    Write-Host "Cozum: python -m venv venv; .\venv\Scripts\activate; pip install -r requirements.txt" -ForegroundColor Yellow
    Pause
    exit 1
}

# .env yoksa otomatik kopyala
if (-not (Test-Path ".env")) {
    Write-Host "[UYARI] .env bulunamadi, .env.example kopyalaniyor..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "[UYARI] Lutfen .env dosyasina API anahtarlarinizi girin." -ForegroundColor Yellow
}

# Turkce karakter destegi
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "[BILGI] FastAPI sunucusu baslatiliyor... (http://localhost:8000)" -ForegroundColor Green
$projectRoot = (Get-Location).Path
Start-Process powershell -ArgumentList `
    "-NoExit", "-Command", `
    "`$env:PYTHONIOENCODING='utf-8'; Set-Location '$projectRoot'; .\venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000"

Write-Host "[BILGI] Sunucu hazir olana kadar bekleniyor (4 sn)..." -ForegroundColor DarkGray
Start-Sleep -Seconds 4

Write-Host "[BILGI] Tarayici aciliyor..." -ForegroundColor Green
Start-Process "http://127.0.0.1:8000/"

Write-Host ""
Write-Host "FinGuard AI calisiyor!" -ForegroundColor Cyan
Write-Host "Durdurmak icin: Acilan PowerShell penceresini kapatin." -ForegroundColor Yellow
Start-Sleep -Seconds 3
