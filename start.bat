@echo off
:: Dosyanin bulundugu dizine gec
cd /d "%~dp0"

echo ===================================================
echo   FinGuard AI - Baslatiliyor...
echo ===================================================

:: Venv kontrolu
if not exist "venv\Scripts\python.exe" (
    echo [HATA] Sanal ortam (venv) bulunamadi!
    echo Cozum: python -m venv venv
    echo        venv\Scripts\activate
    echo        pip install -r requirements.txt
    pause
    exit /b 1
)

:: .env kontrolu
if not exist ".env" (
    echo [UYARI] .env dosyasi bulunamadi! .env.example kopyalanıyor...
    copy ".env.example" ".env" >nul
    echo [UYARI] Lutfen .env dosyasina API anahtarlarinizi girin.
)

:: Türkçe karakter ve konsol ayarlari
set PYTHONIOENCODING=utf-8
chcp 65001 >nul

:: Backend'i venv python ile yeni pencerede baslat
echo [BILGI] FastAPI sunucusu baslatiliyor... (http://localhost:8000)
start "FinGuard Backend" cmd /k "cd /d "%~dp0" && set PYTHONIOENCODING=utf-8 && venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000"

:: Sunucunun acilmasi icin bekle
echo [BILGI] Sunucu hazir olana kadar bekleniyor (4 sn)...
timeout /t 4 /nobreak >nul

:: Tarayicida ac
echo [BILGI] Tarayici aciliyor...
start http://127.0.0.1:8000/

echo.
echo ===================================================
echo   FinGuard AI calisiyor!
echo   Durdurmak icin: FinGuard Backend penceresini kapatin
echo ===================================================
timeout /t 5 /nobreak >nul
exit
