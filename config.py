"""
FinGuard AI - Konfigürasyon
Tüm API anahtarları ve ayarlar buradan yönetilir.

API Key'ler: .env dosyasından okunur (UI'dan girildiğinde .env'ye yazılır)
Model seçimi: DB'den okunur (runtime'da değiştirilebilir)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# .env dosyasını proje kökünden yükle
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)


# Kullanılabilir Gemini modelleri (UI dropdown için)
AVAILABLE_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

DEFAULT_MODEL = "gemini-3.1-flash-lite"


class Settings:
    """Uygulama ayarları — API key'ler .env'den, model seçimi DB'den."""

    # App
    APP_ENV: str = os.getenv("APP_ENV", "development")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))

    def __init__(self):
        self._reload_env()

    def _reload_env(self):
        """API key'leri .env dosyasından yeniden yükler."""
        load_dotenv(ENV_PATH, override=True)
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        self.NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
        self.NOTION_PARENT_PAGE_ID = os.getenv("NOTION_PARENT_PAGE_ID", "")
        self.TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

    @property
    def GEMINI_MODEL(self) -> str:
        """Aktif model — DB'de ayar varsa onu kullan, yoksa varsayılan."""
        try:
            from data.budget_db import get_setting
            model = get_setting("gemini_model", "")
            return model if model else DEFAULT_MODEL
        except Exception:
            return DEFAULT_MODEL

    def set_env_key(self, key: str, value: str):
        """
        .env dosyasına bir key yazar/günceller.
        Sadece bilinen key'leri kabul eder (güvenlik).
        """
        allowed_keys = {
            "GEMINI_API_KEY", "TAVILY_API_KEY",
            "NOTION_API_KEY", "NOTION_PARENT_PAGE_ID"
        }
        if key not in allowed_keys:
            raise ValueError(f"Bilinmeyen ayar: {key}")

        # Mevcut .env içeriğini oku
        env_lines = []
        if ENV_PATH.exists():
            env_lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

        # Key varsa güncelle, yoksa ekle
        found = False
        for i, line in enumerate(env_lines):
            if line.strip().startswith(f"{key}="):
                env_lines[i] = f'{key}="{value}"'
                found = True
                break
        if not found:
            env_lines.append(f'{key}="{value}"')

        # Yaz
        ENV_PATH.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

        # Belleği güncelle
        self._reload_env()

    def validate(self) -> dict:
        """API anahtarlarının varlığını kontrol eder."""
        return {
            "gemini": bool(self.GEMINI_API_KEY),
            "notion": bool(self.NOTION_API_KEY),
            "tavily": bool(self.TAVILY_API_KEY),
        }

    def get_masked_keys(self) -> dict:
        """API key'lerin maskelenmiş halini döndürür (UI gösterimi için)."""
        def mask(val):
            if not val:
                return ""
            if len(val) <= 8:
                return "••••••••"
            return "••••" + val[-4:]

        return {
            "GEMINI_API_KEY": mask(self.GEMINI_API_KEY),
            "TAVILY_API_KEY": mask(self.TAVILY_API_KEY),
            "NOTION_API_KEY": mask(self.NOTION_API_KEY),
            "NOTION_PARENT_PAGE_ID": self.NOTION_PARENT_PAGE_ID or "",
        }


settings = Settings()


# ─── Canonical Category Registry ──────────────────────────────
# Tüm sistem bu listeden okur. Yeni kategori eklemek için sadece buraya ekle.
CATEGORIES = [
    {
        "id": "market",
        "label": "Market",
        "icon": "🛒",
        "default_limit": 4000,
        "keywords": ["süpermarket", "bakkal", "manav", "su", "gıda", "erzak",
                     "temizlik", "deterjan", "şampuan", "market"],
    },
    {
        "id": "restoran",
        "label": "Restoran & Kafe",
        "icon": "☕",
        "default_limit": 1500,
        "keywords": ["kafe", "restoran", "yemek", "kahve", "çay", "fast food",
                     "yemeksepeti", "getir", "trendyol yemek"],
    },
    {
        "id": "ulasim",
        "label": "Ulaşım",
        "icon": "🚗",
        "default_limit": 1500,
        "keywords": ["otobüs", "metro", "taksi", "uber", "benzin", "araç",
                     "uçak", "köprü", "otoyol", "istanbulkart"],
    },
    {
        "id": "fatura",
        "label": "Fatura & Abonelik",
        "icon": "⚡",
        "default_limit": 3000,
        "keywords": ["elektrik", "doğalgaz", "su faturası", "internet",
                     "telefon faturası", "aidat", "sigorta"],
    },
    {
        "id": "eglence",
        "label": "Eğlence",
        "icon": "🎮",
        "default_limit": 1000,
        "keywords": ["sinema", "konser", "oyun", "netflix", "spotify",
                     "steam", "kitap", "müzik"],
    },
    {
        "id": "giyim",
        "label": "Giyim",
        "icon": "👕",
        "default_limit": 2000,
        "keywords": ["kıyafet", "ayakkabı", "çanta", "kemer", "aksesuar",
                     "takı", "tekstil"],
    },
    {
        "id": "saglik",
        "label": "Sağlık",
        "icon": "💊",
        "default_limit": 1000,
        "keywords": ["eczane", "ilaç", "doktor", "hastane", "diş",
                     "spor salonu", "vitamin", "takviye"],
    },
    {
        "id": "egitim",
        "label": "Eğitim",
        "icon": "📚",
        "default_limit": 1500,
        "keywords": ["kurs", "ders", "okul", "sertifika", "udemy",
                     "kitap eğitim", "ansiklopedi"],
    },
    {
        "id": "elektronik",
        "label": "Elektronik",
        "icon": "💻",
        "default_limit": 3000,
        "keywords": ["telefon", "bilgisayar", "tablet", "kulaklık", "klavye",
                     "mouse", "şarj", "akıllı saat", "tv", "kablo", "adaptör"],
    },
    {
        "id": "kirtasiye",
        "label": "Kırtasiye & Ofis",
        "icon": "✏️",
        "default_limit": 500,
        "keywords": ["kalem", "defter", "kağıt", "bant", "ip", "makas",
                     "zımba", "dosya", "yapışkan", "boya", "ofis malzemesi"],
    },
    {
        "id": "kira",
        "label": "Kira",
        "icon": "🏠",
        "default_limit": 10000,
        "keywords": ["kira", "konut", "işyeri kirası", "otel", "konaklama"],
    },
    {
        "id": "diger",
        "label": "Diğer",
        "icon": "💰",
        "default_limit": 2000,
        "keywords": [],  # catch-all
    },
]

# Hızlı erişim için dict versiyonu
CATEGORY_BY_ID = {c["id"]: c for c in CATEGORIES}
