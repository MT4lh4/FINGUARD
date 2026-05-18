"""
FinGuard AI - Notion API Aracı
================================
Notion'a rapor yazan ve okuyan fonksiyonlar.
"""

from notion_client import Client
from config import settings


def get_notion_client() -> Client:
    """Notion client oluşturur"""
    return Client(auth=settings.NOTION_API_KEY)


def create_page(title: str, content_blocks: list[dict], parent_page_id: str = None) -> dict:
    """
    Notion'da yeni bir sayfa oluşturur.
    
    Args:
        title: Sayfa başlığı
        content_blocks: Notion block formatında içerik listesi
        parent_page_id: Üst sayfa ID'si (opsiyonel)
    
    Returns:
        Oluşturulan sayfa bilgileri
    """
    notion = get_notion_client()

    # Parent belirleme
    if parent_page_id:
        parent = {"page_id": parent_page_id}
    elif settings.NOTION_PARENT_PAGE_ID:
        parent = {"page_id": settings.NOTION_PARENT_PAGE_ID}
    else:
        raise ValueError("NOTION_PARENT_PAGE_ID veya parent_page_id gerekli")

    page = notion.pages.create(
        parent=parent,
        properties={
            "title": {
                "title": [{"text": {"content": title}}]
            }
        },
        children=content_blocks
    )
    return page


def create_report_blocks(sections: dict) -> list[dict]:
    """
    Rapor bölümlerinden Notion block'ları oluşturur.
    Markdown tablo formatını Notion table block'una dönüştürür.
    
    Args:
        sections: {"Başlık": "İçerik", ...} formatında bölümler
    
    Returns:
        Notion block listesi
    """
    blocks = []

    for heading, content in sections.items():
        # Başlık ekle
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": heading}}]
            }
        })

        # İçeriği satırlara böl
        lines = content.split("\n") if isinstance(content, str) else [content]
        
        # Markdown tablo satırlarını ayıkla
        table_rows = []
        non_table_lines = []
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                # Ayırıcı satır mı kontrol et (|---|---|)
                inner = stripped[1:-1]
                if all(c in '-| ' for c in inner):
                    continue  # Ayırıcı satırı atla
                # Hücreleri parse et
                cells = [c.strip() for c in stripped[1:-1].split("|")]
                table_rows.append(cells)
            else:
                # Eğer önceki satırlar bir tablo oluşturduysa, önce tabloyu yaz
                if table_rows:
                    blocks.append(_build_notion_table(table_rows))
                    table_rows = []
                if stripped:
                    non_table_lines.append(stripped)
        
        # Kalan tablo satırları
        if table_rows:
            blocks.append(_build_notion_table(table_rows))
            table_rows = []
        
        # Normal paragraflar
        for para in non_table_lines:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": para}}]
                }
            })

    return blocks


def _build_notion_table(rows: list[list[str]]) -> dict:
    """Satır listesinden Notion table block oluşturur."""
    if not rows:
        return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}}
    
    col_count = max(len(r) for r in rows)
    
    table_rows = []
    for row in rows:
        # Eksik sütunları doldur
        cells = row + [""] * (col_count - len(row))
        table_rows.append({
            "type": "table_row",
            "table_row": {
                "cells": [
                    [{"type": "text", "text": {"content": cell}}]
                    for cell in cells
                ]
            }
        })
    
    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": col_count,
            "has_column_header": True,
            "has_row_header": False,
            "children": table_rows
        }
    }


def search_pages(query: str) -> list[dict]:
    """Notion'da sayfa arar"""
    notion = get_notion_client()
    results = notion.search(query=query, filter={"property": "object", "value": "page"})
    return results.get("results", [])


def list_users() -> list[dict]:
    """Notion kullanıcılarını listeler (API bağlantı testi için)"""
    notion = get_notion_client()
    return notion.users.list()
