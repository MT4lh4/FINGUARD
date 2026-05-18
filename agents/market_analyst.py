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
    report_sections: dict    # Bölümlere ayrılmış rapor (__price_table_md__ içermez)
    price_table_md: str      # Gemini'nin fiyat tablosu (markdown)
    price_comparison: list   # Site bazlı fiyat karşılaştırması
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

# ─── Node 2b: Site Fiyat Karşılaştırma ──────────────────────
import re as _re

def _extract_price(text: str) -> float:
    """Metinden TL fiyatı çıkar."""
    text = text or ""
    patterns = [
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?)\s*(?:TL|₺|lira)',
        r'(\d{3,6}(?:[.,]\d{3})*)',
    ]
    for pat in patterns:
        m = _re.search(pat, text, _re.IGNORECASE)
        if m:
            raw = m.group(1).replace('.', '').replace(',', '.')
            try:
                val = float(raw)
                if 10 < val < 1_000_000:
                    return val
            except ValueError:
                pass
    return 0.0


def price_compare_node(state: MarketAnalystState) -> MarketAnalystState:
    """Aynı ürünün TR e-ticaret sitelerindeki fiyatlarını Tavily ile bulur."""
    if state.get("error"):
        return state

    SITES = [
        ("Trendyol",    "trendyol.com"),
        ("Hepsiburada", "hepsiburada.com"),
        ("Amazon TR",   "amazon.com.tr"),
    ]

    results = []
    try:
        for site_name, site_domain in SITES:
            try:
                q = f'{state["query"]} site:{site_domain}'
                r = search_market(q, max_results=2)
                for item in r.get("results", []):
                    price = _extract_price(item.get("content", "") + " " + item.get("title", ""))
                    if price > 0:
                        results.append({
                            "site":  site_name,
                            "price": price,
                            "url":   item.get("url", ""),
                            "title": item.get("title", "")[:60],
                        })
                        break
            except Exception:
                pass

        # En ucuzunu işaretle
        if results:
            min_price = min(r["price"] for r in results)
            for r in results:
                r["is_cheapest"] = (r["price"] == min_price)
                r["diff"] = round(r["price"] - min_price, 0)

    except Exception as e:
        results = []

    return {**state, "price_comparison": results}




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

        # Bölümlere ayır — fiyat bölümü ayrı field'a alınır
        sections, price_table_md = parse_report_sections(analysis)

        return {**state, "analysis": analysis, "report_sections": sections, "price_table_md": price_table_md}
    except Exception as e:
        return {**state, "error": f"Gemini analiz hatası: {str(e)}"}


def parse_report_sections(analysis: str) -> tuple[dict, str]:
    """Analiz metnini bölümlere ayırır.
    Returns: (sections_dict, price_table_md)
    Fiyat bölümü sections'dan çıkarılır, ayrı string olarak döndürülür.
    """
    sections = {}
    current_heading = "Genel"
    current_content = []
    PRICE_KEYWORDS = ("Fiyat Karşılaştırması", "Fiyat Tablosu", "Site Fiyat")

    for line in analysis.split("\n"):
        if line.startswith("### ") or line.startswith("## "):
            if current_content:
                sections[current_heading] = "\n".join(current_content).strip()
            current_heading = line.lstrip("#").strip()
            current_content = []
        else:
            current_content.append(line)

    if current_content:
        sections[current_heading] = "\n".join(current_content).strip()

    # Fiyat bölümünü sections'dan ayır
    price_table_md = ""
    price_key = next(
        (k for k in sections if any(kw in k for kw in PRICE_KEYWORDS)),
        None
    )
    if price_key:
        price_table_md = sections.pop(price_key)

    return sections, price_table_md


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

        # Fiyat Karşılaştırma Tablosu
        price_data = state.get("price_comparison", [])
        price_md   = state.get("price_table_md", "")

        if price_data:
            # Structured array → Notion native table
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "💰 Site Fiyat Karşılaştırması"}}]
                }
            })
            header_row = {
                "object": "block",
                "type": "table_row",
                "table_row": {
                    "cells": [
                        [{"type": "text", "text": {"content": "Site"}}],
                        [{"type": "text", "text": {"content": "Fiyat (₺)"}}],
                        [{"type": "text", "text": {"content": "En Ucuz"}}],
                        [{"type": "text", "text": {"content": "Bağlantı"}}],
                    ]
                }
            }
            data_rows = []
            for p in price_data:
                link_text = p.get("url", "")
                data_rows.append({
                    "object": "block",
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"type": "text", "text": {"content": p.get("site", "")}}],
                            [{"type": "text", "text": {"content": f"{p.get('price', 0):,.0f} ₺"}}],
                            [{"type": "text", "text": {"content": "✅" if p.get("is_cheapest") else ""}}],
                            [{"type": "text", "text": {"content": link_text[:80], "link": {"url": link_text} if link_text.startswith("http") else None}}],
                        ]
                    }
                })
            blocks.append({
                "object": "block",
                "type": "table",
                "table": {
                    "table_width": 4,
                    "has_column_header": True,
                    "has_row_header": False,
                    "children": [header_row] + data_rows
                }
            })
        elif price_md:
            # Gemini markdown tablosunu parse edip Notion native table'a çevir
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "💰 Fiyat Karşılaştırması"}}]
                }
            })
            # Markdown tablo satırlarını parse et
            table_rows = []
            for line in price_md.splitlines():
                line = line.strip()
                if not line.startswith("|"):
                    continue
                # Ayraç satırını atla: |---|---|
                cells_raw = [c.strip() for c in line.split("|") if c.strip()]
                if all(set(c.replace("-", "").replace(":", "")) == set() or c.replace("-","").replace(":","").strip() == "" for c in cells_raw):
                    continue
                notion_row = {
                    "object": "block",
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [{"type": "text", "text": {"content": cell[:200]}}]
                            for cell in cells_raw
                        ]
                    }
                }
                table_rows.append(notion_row)

            if table_rows:
                col_count = max(len(r["table_row"]["cells"]) for r in table_rows)
                # Eksik hücreleri doldur
                for r in table_rows:
                    while len(r["table_row"]["cells"]) < col_count:
                        r["table_row"]["cells"].append([{"type": "text", "text": {"content": ""}}])
                blocks.append({
                    "object": "block",
                    "type": "table",
                    "table": {
                        "table_width": col_count,
                        "has_column_header": True,
                        "has_row_header": False,
                        "children": table_rows
                    }
                })

        # Kaynaklar bölümü
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "📎 Kaynaklar"}}]
            }
        })

        for r in state["search_results"].get("results", [])[:5]:
            url = r.get("url", "")
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{
                        "type": "text",
                        "text": {
                            "content": r.get("title", ""),
                            "link": {"url": url} if url and url.startswith("http") else None,
                        },
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

    graph.add_node("price_compare", price_compare_node)

    graph.add_edge(START, "web_search")
    graph.add_edge("web_search", "data_clean")
    graph.add_edge("data_clean", "price_compare")
    graph.add_edge("price_compare", "gemini_analyze")
    graph.add_edge("gemini_analyze", "notion_write")
    graph.add_edge("notion_write", END)

    return graph.compile()


# Graph instance
market_analyst = build_market_analyst()


def run_market_analyst(query: str) -> dict:
    """Market Analyst'i çalıştırır"""
    result = market_analyst.invoke({
        "query":           query,
        "search_results":  {},
        "cleaned_data":    "",
        "analysis":        "",
        "report_sections": {},
        "price_table_md":  "",
        "price_comparison": [],
        "notion_url":      "",
        "error":           "",
    })
    return {
        "query":            result["query"],
        "analysis":         result["analysis"],
        "report_sections":  result.get("report_sections", {}),
        "price_table_md":   result.get("price_table_md", ""),
        "price_comparison": result.get("price_comparison", []),
        "notion_url":       result["notion_url"],
        "sources":          result["search_results"].get("results", [])[:5],
        "sources_count":    result["search_results"].get("total_results", 0),
        "error":            result["error"],
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
