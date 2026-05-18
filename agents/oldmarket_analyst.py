"""
Market Analyst Agent
====================
Piyasa araştırması yapıp Notion'a rapor yazan agent.

Akış: web_search → data_clean → gemini_analyze → notion_write → END

Kullanım:
    result = run_market_analyst("Mekanik klavye pazarını analiz et")
"""

import sys
import time
import json
from pathlib import Path
from typing import TypedDict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from google import genai
from langgraph.graph import StateGraph, START, END
from config import settings
from tools.web_search import search_market
from tools.notion_tool import get_notion_client, create_report_blocks


# ─── State ─────────────────────────────────────────────────────
class MarketAnalystState(TypedDict):
    query: str               # Kullanıcının araştırma isteği
    search_results: dict     # Tavily arama sonuçları
    cleaned_data: str        # Temizlenmiş veri (Gemini'ye gönderilecek)
    analysis: str            # Gemini'nin analiz raporu
    report_sections: dict    # Bölümlere ayrılmış rapor
    notion_url: str          # Notion'a yazılan raporun URL'si
    error: str               # Hata mesajı (varsa)


# ─── Gemini Client ─────────────────────────────────────────────
client = genai.Client(api_key=settings.GEMINI_API_KEY)


# ─── Node 1: Web Arama ────────────────────────────────────────
def web_search_node(state: MarketAnalystState) -> MarketAnalystState:
    """Tavily ile web araması yapar"""
    try:
        results = search_market(state["query"])
        return {**state, "search_results": results}
    except Exception as e:
        return {**state, "error": f"Web arama hatası: {str(e)}"}


# ─── Node 2: Veri Temizleme ───────────────────────────────────
def data_clean_node(state: MarketAnalystState) -> MarketAnalystState:
    """Ham arama verilerini analiz için temizler ve yapılandırır"""
    if state.get("error"):
        return state

    results = state["search_results"]
    cleaned_parts = []

    # AI özeti ekle
    if results.get("answer_summary"):
        cleaned_parts.append(f"## AI Arama Özeti\n{results['answer_summary']}")

    # Her kaynağı temizle
    for i, r in enumerate(results.get("results", []), 1):
        cleaned_parts.append(
            f"## Kaynak {i}: {r.get('title', 'Bilinmeyen')}\n"
            f"URL: {r.get('url', '')}\n"
            f"İçerik: {r.get('content', '')}\n"
        )

    cleaned = "\n---\n".join(cleaned_parts)
    return {**state, "cleaned_data": cleaned}


# ─── Node 3: Gemini Analiz ────────────────────────────────────
ANALYSIS_PROMPT = """Sen deneyimli bir pazar analisti ve finansal danışmansın. Aşağıdaki web araştırma verilerine dayanarak "{query}" hakkında kapsamlı bir pazar analizi raporu hazırla.

## Toplanan Veriler:
{data}

## Rapor Formatı (Bu başlıkları kullan):

### 📊 Pazar Özeti
Pazarın genel durumu, büyüklüğü ve trendi hakkında özet.

### 💰 Fiyat Karşılaştırması
Ürün/hizmet fiyatlarını tablo halinde sun. Aşağıdaki formatı birebir kullan:
| Ürün/Marka | Fiyat Aralığı | Platform | Değerlendirme |
|---|---|---|---|
(En az 4-5 ürün/marka listele, fiyatlarını TL cinsinden yaz)

### 📈 Büyüme Trendleri
Pazardaki büyüme eğilimleri, gelecek tahminleri.

### 🏢 Öne Çıkan Markalar ve Rakipler
Ana oyuncular, pazar payları ve rekabet durumu.

### 💡 Fırsatlar
Pazardaki fırsatlar ve potansiyel alanlar.

### ⚠️ Riskler ve Tehditler
Dikkat edilmesi gereken riskler.

### 🎯 Tavsiye ve Sonuç
Tüketici veya yatırımcı için somut tavsiyeler.

KURALLLAR:
- Türkçe yaz
- Veri odaklı ol, rakamlar ve yüzdeler kullan
- Her bölüm en az 2-3 cümle olsun
- Fiyat tablosunu MUTLAKA markdown tablo formatında yaz
- Kaynakları referans göster
- Profesyonel ve okunabilir bir dil kullan"""


def gemini_analyze_node(state: MarketAnalystState) -> MarketAnalystState:
    """Gemini ile toplanan verileri analiz eder"""
    if state.get("error"):
        return state

    try:
        time.sleep(2)  # Rate limit koruması

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=ANALYSIS_PROMPT.format(
                query=state["query"],
                data=state["cleaned_data"][:8000]  # Token limiti için kırp
            )
        )
        analysis = response.text

        # Bölümlere ayır
        sections = parse_report_sections(analysis)

        return {**state, "analysis": analysis, "report_sections": sections}
    except Exception as e:
        return {**state, "error": f"Gemini analiz hatası: {str(e)}"}


def parse_report_sections(analysis: str) -> dict:
    """Analiz metnini bölümlere ayırır"""
    sections = {}
    current_heading = "Genel"
    current_content = []

    for line in analysis.split("\n"):
        if line.startswith("### "):
            if current_content:
                sections[current_heading] = "\n".join(current_content).strip()
            current_heading = line.replace("### ", "").strip()
            current_content = []
        elif line.startswith("## "):
            if current_content:
                sections[current_heading] = "\n".join(current_content).strip()
            current_heading = line.replace("## ", "").strip()
            current_content = []
        else:
            current_content.append(line)

    if current_content:
        sections[current_heading] = "\n".join(current_content).strip()

    return sections


# ─── Node 4: Notion'a Yaz ─────────────────────────────────────
def notion_write_node(state: MarketAnalystState) -> MarketAnalystState:
    """Analiz raporunu Notion'a yazar"""
    if state.get("error"):
        return state

    try:
        notion = get_notion_client()
        now = datetime.now().strftime("%d.%m.%Y %H:%M")
        title = f"📊 Pazar Analizi: {state['query']} — {now}"

        # Notion block'ları oluştur
        blocks = []

        # Üst bilgi
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": f"Bu rapor FinGuard AI Market Analyst tarafından {now} tarihinde otomatik oluşturulmuştur."}}],
                "icon": {"type": "emoji", "emoji": "🤖"},
            }
        })

        # Arama özeti
        if state["search_results"].get("answer_summary"):
            blocks.append({
                "object": "block",
                "type": "toggle",
                "toggle": {
                    "rich_text": [{"type": "text", "text": {"content": "🔍 Kaynak Verileri (Tıkla)"}}],
                    "children": [{
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": state["search_results"]["answer_summary"][:2000]}}]
                        }
                    }]
                }
            })

        # Analiz bölümlerini ekle
        blocks.extend(create_report_blocks(state["report_sections"]))

        # Kaynaklar bölümü
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "📎 Kaynaklar"}}]
            }
        })

        for r in state["search_results"].get("results", [])[:5]:
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": r.get("title", ""), "link": {"url": r.get("url", "")}},
                    }]
                }
            })

        # Notion'a yaz
        if settings.NOTION_PARENT_PAGE_ID:
            # Parent page varsa alt sayfa olarak yaz
            page = notion.pages.create(
                parent={"page_id": settings.NOTION_PARENT_PAGE_ID},
                properties={
                    "title": {"title": [{"text": {"content": title}}]}
                },
                children=blocks
            )
        else:
            # Database yoksa search ile bir sayfa bul ve alt sayfa olarak yaz
            search_results = notion.search(query="FinGuard", filter={"property": "object", "value": "page"})
            pages = search_results.get("results", [])

            if pages:
                parent_id = pages[0]["id"]
            else:
                # Hiç sayfa bulunamazsa workspace'e yaz
                # Önce boş bir sayfa oluştur
                parent_page = notion.pages.create(
                    parent={"workspace": True},
                    properties={
                        "title": {"title": [{"text": {"content": "📊 FinGuard AI Raporları"}}]}
                    }
                )
                parent_id = parent_page["id"]

            page = notion.pages.create(
                parent={"page_id": parent_id},
                properties={
                    "title": {"title": [{"text": {"content": title}}]}
                },
                children=blocks
            )

        notion_url = page.get("url", "")
        return {**state, "notion_url": notion_url}

    except Exception as e:
        # Notion hatası olsa bile analiz sonucunu döndür
        return {**state, "notion_url": "", "error": f"Notion yazma hatası: {str(e)} (Analiz tamamlandı)"}


# ─── Graph Oluştur ────────────────────────────────────────────
def build_market_analyst():
    """Market Analyst graph'ını oluşturur"""
    graph = StateGraph(MarketAnalystState)

    graph.add_node("web_search", web_search_node)
    graph.add_node("data_clean", data_clean_node)
    graph.add_node("gemini_analyze", gemini_analyze_node)
    graph.add_node("notion_write", notion_write_node)

    graph.add_edge(START, "web_search")
    graph.add_edge("web_search", "data_clean")
    graph.add_edge("data_clean", "gemini_analyze")
    graph.add_edge("gemini_analyze", "notion_write")
    graph.add_edge("notion_write", END)

    return graph.compile()


# Graph instance
market_analyst = build_market_analyst()


def run_market_analyst(query: str) -> dict:
    """Market Analyst'i çalıştırır"""
    result = market_analyst.invoke({
        "query": query,
        "search_results": {},
        "cleaned_data": "",
        "analysis": "",
        "report_sections": {},
        "notion_url": "",
        "error": "",
    })
    return {
        "query": result["query"],
        "analysis": result["analysis"],
        "report_sections": result.get("report_sections", {}),
        "notion_url": result["notion_url"],
        "sources": result["search_results"].get("results", [])[:5],
        "sources_count": result["search_results"].get("total_results", 0),
        "error": result["error"],
    }


# ─── Test ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding='utf-8')

    print("🤖 Market Analyst Agent - Uçtan Uca Test")
    print("=" * 60)

    query = "Mekanik klavye pazarını analiz et"
    print(f"\n📝 Sorgu: \"{query}\"")
    print("⏳ Analiz ediliyor (web arama → analiz → Notion)...\n")

    result = run_market_analyst(query)

    if result["error"]:
        print(f"⚠️ Hata: {result['error']}")

    print(f"\n📊 Analiz ({result['sources_count']} kaynak kullanıldı):")
    print("-" * 60)
    print(result["analysis"][:1500])

    if result["notion_url"]:
        print(f"\n📝 Notion Raporu: {result['notion_url']}")
    else:
        print("\n📝 Notion'a yazılamadı (database ID olmadan devam edildi)")

    print("\n✅ Market Analyst testi tamamlandı!")
