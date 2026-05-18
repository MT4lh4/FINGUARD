"""
Impulse Guard Agent
===================
Kullanıcıyı dürtüsel alışverişlerden koruyan finansal vicdan ajanı.

Akış: analyze_product → check_budget → generate_intervention → END
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
from config import settings, CATEGORIES, CATEGORY_BY_ID
from tools.web_search import search_web


# ─── State ─────────────────────────────────────────────────────
class ImpulseGuardState(TypedDict):
    product_intent: str       # Kullanıcının almak istediği ürün/durum
    product_price: float      # Tahmini veya girilen fiyat (opsiyonel)
    product_category: str     # Ürün kategorisi
    search_results: str       # Ürünle ilgili web arama (alternatifler vs)
    budget_status: dict       # Kullanıcının o anki bütçe durumu
    intervention: str         # Gemini'nin müdahale/koçluk metni
    action_decision: str      # "BEKLE", "AL", "ALTERNATIF_BAK", "IPTAL_ET"
    error: str


# ─── Gemini Client ─────────────────────────────────────────────
client = genai.Client(api_key=settings.GEMINI_API_KEY)


# ─── Node 1: Ürün Analizi (Web Arama) ─────────────────────────
def analyze_product_node(state: ImpulseGuardState) -> ImpulseGuardState:
    """Alınmak istenen ürünle ilgili piyasa/fiyat/alternatif araştırması yapar"""
    if state.get("error"):
        return state

    product = state["product_intent"]

    try:
        # 1) Fiyat & yorum araması
        price_query = f"{product} fiyat yorum 2025 türkiye"
        price_results = search_web(price_query, max_results=3)

        search_data = ""
        if price_results.get("answer"):
            search_data += f"Fiyat/Yorum Özeti: {price_results['answer']}\n"
        for r in price_results.get("results", []):
            search_data += f"- {r.get('title')}: {r.get('content', '')[:200]}\n"

        # 2) Alternatif ürün araması
        alt_query = f"{product} daha ucuz alternatif muadil"
        alt_results = search_web(alt_query, max_results=3)

        alt_data = ""
        if alt_results.get("answer"):
            alt_data += f"Alternatif Özeti: {alt_results['answer']}\n"
        for r in alt_results.get("results", []):
            alt_data += f"- {r.get('title')}: {r.get('content', '')[:200]}\n"

        # 3) Kategori tespiti
        category = "diger"
        try:
            valid_cats = [c["id"] for c in CATEGORIES]
            cat_examples = "\n".join(
                f'- "{c["keywords"][0] if c["keywords"] else c["label"]}" → {c["id"]}'
                for c in CATEGORIES
            )
            cat_prompt = f"""Aşağıdaki ürün için EN UYGUN kategoriyi seç.
Ürün: "{product}"

Sadece şu id'lerden birini yaz, başka hiçbir şey yazma:
{', '.join(valid_cats)}

Örnekler:
{cat_examples}"""

            cat_response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=cat_prompt,
            )
            detected = cat_response.text.strip().lower().replace(" ", "")
            if detected in valid_cats:
                category = detected
        except Exception:
            pass

        combined_search = f"{search_data}\n--- ALTERNATIFLER ---\n{alt_data}"
        return {**state, "search_results": combined_search, "product_category": category}

    except Exception as e:
        return {**state, "error": f"Ürün araştırma hatası: {str(e)}"}


# ─── Node 2: Bütçe Kontrolü ─────────────────────────────────────
# Config'den otomatik üret — artık burayı elle düzenleme
DEFAULT_LIMITS = {c["id"]: c["default_limit"] for c in CATEGORIES}

# Display label → db id eşlemesi (Gemini bazen label döndürüyor)
CATEGORY_MAP = {c["id"]: c["id"] for c in CATEGORIES}
CATEGORY_MAP.update({c["label"]: c["id"] for c in CATEGORIES})
# Türkçe karakter varyantları
CATEGORY_MAP.update({
    "Ulasim": "ulasim", "ulaşım": "ulasim",
    "Saglik": "saglik", "Sağlık": "saglik",
    "Egitim": "egitim", "Eğitim": "egitim",
    "Kirtasiye": "kirtasiye", "Kırtasiye": "kirtasiye",
    "Eglence": "eglence", "Eğlence": "eglence",
    "Diger": "diger", "Diğer": "diger",
    "Genel": "diger",
})


def check_budget_node(state: ImpulseGuardState) -> ImpulseGuardState:
    if state.get("error"):
        return state

    try:
        from data.budget_db import (
            get_monthly_summary, get_limit_for_month, get_all_budget_limits
        )

        category = state.get("product_category", "diger")
        db_category = CATEGORY_MAP.get(category, category.lower())

        now = datetime.now()
        summary = get_monthly_summary(month=now.month, year=now.year)

        # Kategori bazlı harcama
        cat_spent = summary["by_category"].get(db_category, 0) if db_category else 0

        # Dönem bazlı limit: bu ay için kayıtlı limit
        cat_limit = get_limit_for_month(db_category, now.month, now.year)
        if cat_limit <= 0:
            cat_limit = DEFAULT_LIMITS.get(db_category, 2000)

        # Toplam limit: tüm kategorilerin bu ay limitlerinin toplamı
        all_limits = get_all_budget_limits()
        toplam_limit = sum(row["monthly_limit"] for row in all_limits) if all_limits else 15000

        price = state.get("product_price", 0) or 0
        remaining_cat = round(cat_limit - cat_spent, 2)
        remaining_total = round(toplam_limit - summary["total"], 2)

        # ── Karar Matrisi (5 seviye) ──────────────────────────
        #  1. HAYIR_BUTCE_YOK  : toplam kalan < 0   (borç bölgesi)
        #  2. KESİNLİKLE ALMA  : kategori bütçesi yetersiz VEYA toplam kalan < fiyat
        #  3. BEKLE            : kategori kalan < fiyat * 1.2 (tampon)
        #  4. ALTERNATİFLERE BAK : kategori kalan < fiyat * 2  ama yeterli
        #  5. ONAYLA           : kategori kalan >= fiyat * 2
        pre_decision = "BELIRSIZ"
        if remaining_total < 0:
            pre_decision = "HAYIR_BUTCE_YOK"
        elif price > 0 and remaining_cat < price:
            pre_decision = "KESİNLİKLE ALMA"
        elif price > 0 and remaining_cat < price * 1.2:
            pre_decision = "BEKLE"
        elif price > 0 and remaining_cat < price * 2:
            pre_decision = "ALTERNATİFLERE BAK"
        elif price > 0:
            pre_decision = "ONAYLA"
        # Fiyat bilinmiyorsa → Gemini karar versin (BELIRSIZ)

        budget_status = {
            "aylik_limit": cat_limit,
            "harcanan": cat_spent,
            "kalan": remaining_cat,
            "toplam_limit": toplam_limit,
            "toplam_harcanan": summary["total"],
            "toplam_kalan": remaining_total,
            "pre_decision": pre_decision,   # Gemini'ye ipucu
            "bütçe_doluluğu": round(cat_spent / cat_limit * 100, 1) if cat_limit > 0 else 0,
        }

    except Exception as e:
        budget_status = {
            "aylik_limit": 3000, "harcanan": 0, "kalan": 3000,
            "toplam_limit": 15000, "toplam_harcanan": 0, "toplam_kalan": 15000,
            "pre_decision": "BELIRSIZ", "bütçe_doluluğu": 0,
        }

    return {**state, "budget_status": budget_status}


# ─── Node 3: Gemini Müdahale / Koçluk ─────────────────────────
INTERVENTION_PROMPT = """Sen kullanıcının 'Finansal Vicdanı' ve sert ama sevecen kişisel finans koçusun.
Kullanıcı şu an dürtüsel (gereksiz) bir alışveriş yapmak üzere ve sana danışıyor. Onu koruman lazım!

## Kullanıcının Almak İstediği Şey:
{product}
Tahmini/Belirtilen Fiyat: {price} TL

## Bütçe Durumu ({category} Kategorisi):
- Bu ayki limit: {aylik_limit} TL
- Şimdiye kadar harcanan: {harcanan} TL  ({butce_dolulugu}% doldu)
- Kalan Kategori Bütçesi: {kalan} TL
- Toplam Kalan Bütçe (tüm kategoriler): {toplam_kalan} TL

## İnternetten Bulunan Veriler (Fiyatlar, Yorumlar, Alternatifler):
{search_results}

## Sistem Ön Kararı (bütçe hesabına göre önerim):
{pre_decision}

KESİN KARAR KURALLARI — bunları kesinlikle uygula:
- HAYIR_BUTCE_YOK → toplam bütçe negatife düştü → kesinlikle "KESİNLİKLE ALMA"
- KESİNLİKLE ALMA → kategori bütçesi bu ürüne yetmiyor
- BEKLE → kategori bütçesi yeterli ama çok az tampon var (fiyat * 1.2 içinde)
- ALTERNATİFLERE BAK → bütçe yeterli ama internette daha iyi fiyatlar var
- ONAYLA → bütçe rahat, ürün iyi yorumlu → "AL"
- BELIRSIZ → sen karar ver, bütçe verilerini yorumla

GÖREVLERİN:
1. Sistem ön kararını göz önünde bulundurarak KESİN bir eylem kararı ver.
   Seçenekler: "AL", "BEKLE", "ALTERNATİFLERE BAK", "KESİNLİKLE ALMA"
2. Kararını sert ama esprili ve empatik bir dille açıkla.
3. Bütçe verilerini yüzüne vur! (Örn: "Bu ay %{butce_dolulugu} bütçeni harcadın, o klavye 2000 TL!")
4. İnternet verisine dayanarak daha uygun fiyatlı somut bir alternatif öner (marka + fiyat aralığı ver).
5. "Şu an almazsan bu parayla ne yapabilirsin?" sorusunu sorarak fırsat maliyetini hatırlat.

Çıktıyı şu JSON formatında ver (Markdown kod bloğu KULLANMA, sadece JSON):
{{
    "decision": "BEKLE",
    "message": "Senin için yazdığın harika ve uzun koçluk mesajı buraya gelecek..."
}}"""


def generate_intervention_node(state: ImpulseGuardState) -> ImpulseGuardState:
    """Gemini ile dürtüsel alışverişe müdahale metni üretir"""
    if state.get("error"):
        return state

    try:
        time.sleep(2)  # Rate limit
        
        budget = state["budget_status"]
        prompt = INTERVENTION_PROMPT.format(
            product=state["product_intent"],
            price=state["product_price"] if state["product_price"] > 0 else "Bilinmiyor",
            category=state["product_category"],
            aylik_limit=budget["aylik_limit"],
            harcanan=budget["harcanan"],
            butce_dolulugu=budget.get("bütçe_doluluğu", 0),
            kalan=budget["kalan"],
            toplam_kalan=budget["toplam_kalan"],
            pre_decision=budget.get("pre_decision", "BELIRSIZ"),
            search_results=state["search_results"][:2000]
        )

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )
        
        # JSON parse işlemi (Gemini bazen ```json etiketi koyabilir)
        text = response.text.replace("```json", "").replace("```", "").strip()
        result_json = json.loads(text)

        return {
            **state, 
            "action_decision": result_json.get("decision", "BEKLE"),
            "intervention": result_json.get("message", "Karar alınamadı.")
        }

    except Exception as e:
        return {**state, "error": f"Gemini müdahale hatası: {str(e)}\nHam Çıktı: {response.text if 'response' in locals() else ''}"}


# ─── Graph Oluştur ────────────────────────────────────────────
def build_impulse_guard():
    """Impulse Guard graph'ını oluşturur"""
    graph = StateGraph(ImpulseGuardState)

    graph.add_node("analyze_product", analyze_product_node)
    graph.add_node("check_budget", check_budget_node)
    graph.add_node("generate_intervention", generate_intervention_node)

    graph.add_edge(START, "analyze_product")
    graph.add_edge("analyze_product", "check_budget")
    graph.add_edge("check_budget", "generate_intervention")
    graph.add_edge("generate_intervention", END)

    return graph.compile()


# Graph instance
impulse_guard = build_impulse_guard()


def run_impulse_guard(product: str, price: float = 0.0) -> dict:
    """Impulse Guard'ı çalıştırır"""
    result = impulse_guard.invoke({
        "product_intent": product,
        "product_price": price,
        "product_category": "",
        "search_results": "",
        "budget_status": {},
        "intervention": "",
        "action_decision": "",
        "error": "",
    })

    return {
        "product": result["product_intent"],
        "category": result["product_category"],
        "decision": result["action_decision"],
        "intervention": result["intervention"],
        "budget_status": result["budget_status"],
        "search_results": result.get("search_results", ""),
        "error": result["error"],
    }


# ─── Test ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print("  🛡️ Impulse Guard Agent - Test")
    print("=" * 60)

    # Test Senaryosu: Bütçesi tükenmiş kategoride pahalı bir ürün
    product_query = "SteelSeries Apex Pro Mekanik Klavye"
    price_guess = 5500.0
    
    print(f"\n🛒 Kullanıcının Almak İstediği: {product_query} ({price_guess} TL)")
    print("⏳ Vicdan muhasebesi yapılıyor (Web Arama → Bütçe Kontrolü → Gemini)...\n")

    result = run_impulse_guard(product_query, price_guess)

    if result.get("error"):
        print(f"⚠️ Hata: {result['error']}")
    else:
        print(f"📂 Kategori: {result['category']}")
        print(f"💳 Bütçe Durumu: {result['budget_status']['kalan']} TL kaldı (Harcanan: {result['budget_status']['harcanan']} / {result['budget_status']['aylik_limit']})")
        print(f"🛑 KARAR: {result['decision']}\n")
        print("-" * 60)
        print(f"🗣️ FINGUARD DİYOR Kİ:\n{result['intervention']}")
        print("-" * 60)

    print("\n✅ Impulse Guard testi tamamlandı!")
