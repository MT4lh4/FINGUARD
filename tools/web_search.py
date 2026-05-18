"""
FinGuard AI - Web Arama Aracı (Tavily)
========================================
AI-optimize edilmiş web arama fonksiyonları.
"""

from tavily import TavilyClient
from config import settings


def get_tavily_client() -> TavilyClient:
    """Tavily client oluşturur"""
    return TavilyClient(api_key=settings.TAVILY_API_KEY)


def search_web(query: str, max_results: int = 5) -> dict:
    """
    Tavily ile web araması yapar.
    
    Args:
        query: Arama sorgusu
        max_results: Maksimum sonuç sayısı
    
    Returns:
        Arama sonuçları listesi
    """
    client = get_tavily_client()
    response = client.search(
        query=query,
        max_results=max_results,
        search_depth="advanced",
        include_answer=True,
    )
    return response


def search_market(product_or_topic: str, max_results: int = 3) -> dict:
    """
    Piyasa araştırması için özelleştirilmiş arama.
    Birden fazla açıdan arar ve sonuçları birleştirir.
    
    Args:
        product_or_topic: Araştırılacak ürün veya konu
        max_results: Her sorgu için maksimum sonuç sayısı
    
    Returns:
        Birleştirilmiş arama sonuçları
    """
    client = get_tavily_client()

    # Farklı açılardan ara
    queries = [
        f"{product_or_topic} pazar analizi 2024 2025",
        f"{product_or_topic} fiyat karşılaştırma",
        f"{product_or_topic} kullanıcı yorumları",
    ]

    all_results = []
    answer_summary = ""

    for q in queries:
        try:
            response = client.search(
                query=q,
                max_results=max_results,
                search_depth="advanced",
                include_answer=True,
            )
            all_results.extend(response.get("results", []))
            if response.get("answer"):
                answer_summary += response["answer"] + "\n\n"
        except Exception as e:
            print(f"Arama hatası ({q}): {e}")
            continue

    # Tekrarlı sonuçları kaldır (URL bazlı)
    seen_urls = set()
    unique_results = []
    for r in all_results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique_results.append(r)

    return {
        "query": product_or_topic,
        "answer_summary": answer_summary.strip(),
        "results": unique_results,
        "total_results": len(unique_results),
    }
