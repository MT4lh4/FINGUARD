"""
FinGuard AI - Notion Sayfa Oluşturucu
========================================
Notion'da FinGuard raporları için ana sayfa oluşturur.
Oluşan sayfa ID'sini .env dosyasına eklemelisin.
"""

import sys
import os
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.notion_tool import get_notion_client


def setup_notion():
    notion = get_notion_client()

    # Mevcut sayfaları ara
    print("🔍 Mevcut Notion sayfaları aranıyor...")
    results = notion.search(query="", filter={"property": "object", "value": "page"})
    pages = results.get("results", [])

    print(f"   {len(pages)} sayfa bulundu:")
    for p in pages[:10]:
        title_parts = p.get("properties", {}).get("title", {}).get("title", [])
        title = title_parts[0]["plain_text"] if title_parts else "İsimsiz"
        print(f"   - {title}")
        print(f"     ID: {p['id']}")
        print(f"     URL: {p.get('url', '?')}")
        print()

    if pages:
        print("=" * 60)
        print("⬆️ Yukarıdaki sayfa ID'lerinden birini kullanabilirsin.")
        print("Bu ID'yi .env dosyasına ekle:")
        print(f"   NOTION_PARENT_PAGE_ID={pages[0]['id']}")


if __name__ == "__main__":
    setup_notion()
