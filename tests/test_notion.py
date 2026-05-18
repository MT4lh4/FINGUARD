"""
FinGuard AI - Notion API Bağlantı Testi
=========================================
Gün 2 kontrolü: Notion API çalışıyor mu?
"""

import sys
import os
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.notion_tool import get_notion_client, search_pages


def test_notion():
    """Notion API bağlantısını test eder"""
    print("📝 Notion API testi başlıyor...")

    notion = get_notion_client()

    # Kullanıcı bilgisini al (basit bağlantı testi)
    print("\n1️⃣ Kullanıcı bilgisi alınıyor...")
    try:
        users = notion.users.list()
        print(f"   ✅ Bağlantı başarılı! {len(users['results'])} kullanıcı bulundu.")
        for user in users["results"]:
            print(f"      - {user.get('name', 'İsimsiz')} ({user.get('type', '?')})")
    except Exception as e:
        print(f"   ❌ Hata: {e}")
        return

    # Sayfa arama testi
    print("\n2️⃣ Sayfa arama testi...")
    try:
        results = search_pages("FinGuard")
        print(f"   ✅ Arama başarılı! {len(results)} sonuç bulundu.")
    except Exception as e:
        print(f"   ⚠️ Arama hatası (normal olabilir): {e}")

    print("\n✅ Notion API bağlantısı çalışıyor!")


if __name__ == "__main__":
    test_notion()
