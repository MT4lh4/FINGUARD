import os
import subprocess
import time
import webbrowser
import sys
from pathlib import Path

def main():
    print("===================================================")
    print("   FinGuard AI - Akilli Baslatici (v1.1)")
    print("===================================================")
    
    # Proje kok dizinine git
    project_root = Path(__file__).parent.absolute()
    os.chdir(project_root)
    
    # Python executable yolunu belirle
    python_exe = project_root / "venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        print(f"[HATA] venv bulunamadi: {python_exe}")
        print("Lutfen sanal ortamin kurulu oldugundan emin olun.")
        return

    # Uvicorn komutu
    cmd = [
        str(python_exe), 
        "-m", "uvicorn", 
        "api.main:app", 
        "--host", "127.0.0.1", 
        "--port", "8000"
    ]
    
    print(f"[BILGI] Backend baslatiliyor...")
    
    # Windows'ta yeni bir konsol penceresinde baslat (kullanici loglari gorebilsin diye)
    try:
        if sys.platform == "win32":
            proc = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            proc = subprocess.Popen(cmd)
            
        print("[BILGI] Sunucunun hazir olmasi bekleniyor (3 sn)...")
        time.sleep(3)
        
        # Tarayiciyi ac
        url = "http://127.0.0.1:8000"
        print(f"[BILGI] Tarayici aciliyor: {url}")
        webbrowser.open(url)
        
        print("\n[OK] FinGuard AI basariyla baslatildi!")
        print("Sistemi kapatmak icin acilan siyah komut penceresini kapatin.")
        time.sleep(2)
        
    except Exception as e:
        print(f"[HATA] Baslatma sirasinda bir sorun olustu: {e}")

if __name__ == "__main__":
    main()
