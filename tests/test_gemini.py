"""
FinGuard AI - Gemini API Bağlantı Testi
=========================================
Gun 1 kontrolu: Gemini API calisiyor mu?
Yeni google.genai SDK kullaniliyor.
"""

import sys
import os
from pathlib import Path

# Windows encoding fix
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8')

# Proje kokunu path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))

from google import genai
from config import settings


def test_gemini():
    """Gemini API baglantisini test eder"""
    print("🔑 Gemini API testi başlıyor...")
    print(f"   Model: {settings.GEMINI_MODEL}")

    # Yeni SDK ile client olustur
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Basit test
    print("\n📤 Test mesajı gönderiliyor...")
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents="Sen FinGuard AI finansal asistanısın. Kendini kısaca tanıt."
    )
    print(f"📥 Yanıt:\n{response.text}")

    # Finansal analiz testi
    print("\n" + "=" * 50)
    print("📤 Finansal analiz testi...")
    response2 = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents="""Kullanıcı şunu yazdı: "Bugün 150 TL markete, 45 TL kahveye harcadım"
        
        Bu metinden harcama bilgilerini JSON formatında çıkar:
        [{"miktar": ..., "kategori": ..., "aciklama": ...}]
        
        Sadece JSON döndür."""
    )
    print(f"📥 Yanıt:\n{response2.text}")

    print("\n✅ Gemini API bağlantısı başarılı!")


if __name__ == "__main__":
    test_gemini()
