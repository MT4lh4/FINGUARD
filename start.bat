@echo off
:: Dosyanin bulundugu dizine gec
cd /d "%~dp0"

echo ===================================================
echo   FinGuard AI - Baslatiliyor...
echo ===================================================

:: Venv kontrolu
if not exist "venv\Scripts\python.exe" (
    echo [HATA] Sanal ortam (venv) bulunamadi!
    echo Lutfen projenin kurulu oldugundan emin olun.
    pause
    exit /b 1
)

:: Backend'i doğrudan venv python ile başlat (&& hatasını önlemek için)
echo [BILGI] FastAPI sunucusu baslatiliyor... (localhost:8000)
start "FinGuard Backend" cmd /k "venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000"

:: Sunucunun acilmasi icin bekle
timeout /t 3 /nobreak > nul

:: Tarayicida ac
echo [BILGI] Tarayici aciliyor...
start http://127.0.0.1:8000/

echo.
echo ===================================================
echo   Uygulamayi kapatmak icin siyah pencereyi kapatin.
echo ===================================================
timeout /t 5
exit
