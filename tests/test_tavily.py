"""
FinGuard AI - Tavily API Bağlantı Testi
=========================================
Gün 2 kontrolü: Tavily web arama çalışıyor mu?
"""

import sys
import os
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.web_search import search_web


def test_tavily():
    """Tavily API bağlantısını test eder"""
    print("🔍 Tavily API testi başlıyor...")

    # Basit arama testi
    print("\n📤 Arama: 'mekanik klavye pazar analizi 2025'")
    try:
        result = search_web("mekanik klavye pazar analizi 2025", max_results=3)

        if result.get("answer"):
            print(f"\n💡 AI Özet:\n{result['answer'][:300]}...")

        print(f"\n📋 {len(result.get('results', []))} sonuç bulundu:")
        for i, r in enumerate(result.get("results", []), 1):
            print(f"   {i}. {r['title'][:60]}")
            print(f"      🔗 {r['url'][:80]}")
            print(f"      📄 {r['content'][:100]}...")
            print()

        print("✅ Tavily API bağlantısı başarılı!")

    except Exception as e:
        print(f"❌ Hata: {e}")


if __name__ == "__main__":
    test_tavily()
