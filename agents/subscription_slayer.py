"""
Subscription Slayer Agent
=========================
Hayalet abonelikleri tespit edip iptal tavsiyesi veren agent.

Akış: data_load → analyze_usage → detect_ghosts → generate_advice

Kullanım:
    result = run_subscription_slayer()
    result = run_subscription_slayer(custom_subscriptions=[...])
"""

import sys
import time
import json
from pathlib import Path
from typing import TypedDict
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from google import genai
from langgraph.graph import StateGraph, START, END
from config import settings
from tools.web_search import search_web


# ─── State ─────────────────────────────────────────────────────
class SubscriptionSlayerState(TypedDict):
    subscriptions: list[dict]       # Ham abonelik listesi
    usage_analysis: list[dict]      # Kullanım analizi (her abonelik için)
    ghost_subscriptions: list[dict] # Hayalet (kullanılmayan) abonelikler
    active_subscriptions: list[dict]# Aktif kullanılan abonelikler
    cost_summary: dict              # Maliyet özeti
    advice: str                     # Gemini'nin iptal/optimizasyon tavsiyesi
    report: dict                    # Son rapor
    error: str


# ─── Gemini Client ─────────────────────────────────────────────
client = genai.Client(api_key=settings.GEMINI_API_KEY)

# ─── Mock Data Path ────────────────────────────────────────────
MOCK_DATA_PATH = Path(__file__).parent.parent / "data" / "mock_subscriptions.json"

CATEGORY_LABELS = {
    "entertainment": "Eglence",
    "productivity": "Uretkenlik",
    "education": "Egitim",
    "health": "Saglik",
    "cloud_storage": "Bulut Depolama",
    "shopping": "Alisveris",
    "security": "Guvenlik",
}

# ─── Node 1: Veri Yukleme ─────────────────────────────────────
def data_load_node(state: SubscriptionSlayerState) -> SubscriptionSlayerState:
    """Abonelik verilerini yukler (mock JSON veya kullanici girdisi)"""
    try:
        if state["subscriptions"]:
            return state

        if MOCK_DATA_PATH.exists():
            with open(MOCK_DATA_PATH, "r", encoding="utf-8") as f:
                subs = json.load(f)
            return {**state, "subscriptions": subs}
        else:
            return {**state, "error": "Abonelik verisi bulunamadi. Lutfen veri giriniz."}
    except Exception as e:
        return {**state, "error": f"Veri yukleme hatasi: {str(e)}"}


# ─── Node 2: Kullanim Analizi ─────────────────────────────────
def analyze_usage_node(state: SubscriptionSlayerState) -> SubscriptionSlayerState:
    """Her aboneligin kullanim durumunu analiz eder"""
    if state.get("error"):
        return state

    today = datetime.now()
    analysis = []

    for sub in state["subscriptions"]:
        monthly_cost = sub["amount"]
        if sub["period"] == "yearly":
            monthly_cost = sub["amount"] / 12

        start_date = datetime.strptime(sub["start_date"], "%Y-%m-%d")
        total_months = max(1, (today - start_date).days // 30)
        total_spent = monthly_cost * total_months

        # Eskidikçe "unutulmuş" olma (hayalet) ihtimali artar
        if total_months >= 18:
            usage_status = "hayalet"
            usage_score = 10
        elif total_months >= 12:
            usage_status = "cok_dusuk"
            usage_score = 30
        elif total_months >= 6:
            usage_status = "dusuk_kullanim"
            usage_score = 70
        else:
            usage_status = "aktif"
            usage_score = 100

        analysis.append({
            **sub,
            "months_active": total_months,
            "usage_status": usage_status,
            "usage_score": usage_score,
            "monthly_cost": round(monthly_cost, 2),
            "total_spent": round(total_spent, 2),
            "category_label": CATEGORY_LABELS.get(sub.get("category", ""), sub.get("category", "")),
        })

    return {**state, "usage_analysis": analysis}


# ─── Node 3: Hayalet Tespit ───────────────────────────────────
def detect_ghosts_node(state: SubscriptionSlayerState) -> SubscriptionSlayerState:
    """Hayalet (kullanilmayan) abonelikleri tespit eder ve maliyet ozeti cikarir"""
    if state.get("error"):
        return state

    ghosts = []
    actives = []

    for sub in state["usage_analysis"]:
        if sub["usage_score"] <= 30:
            ghosts.append(sub)
        else:
            actives.append(sub)

    ghost_monthly = sum(s["monthly_cost"] for s in ghosts)
    ghost_yearly = ghost_monthly * 12
    active_monthly = sum(s["monthly_cost"] for s in actives)
    total_monthly = ghost_monthly + active_monthly
    total_wasted = sum(s["total_spent"] for s in ghosts if s["usage_score"] <= 10)

    by_category = {}
    for sub in state["usage_analysis"]:
        cat = sub.get("category_label", "Diger")
        if cat not in by_category:
            by_category[cat] = 0
        by_category[cat] += sub["monthly_cost"]
    by_category = {k: round(v, 2) for k, v in sorted(by_category.items(), key=lambda x: -x[1])}

    cost_summary = {
        "total_monthly": round(total_monthly, 2),
        "total_yearly": round(total_monthly * 12, 2),
        "ghost_monthly": round(ghost_monthly, 2),
        "ghost_yearly": round(ghost_yearly, 2),
        "active_monthly": round(active_monthly, 2),
        "potential_savings_yearly": round(ghost_yearly, 2),
        "total_wasted_so_far": round(total_wasted, 2),
        "ghost_count": len(ghosts),
        "active_count": len(actives),
        "total_count": len(state["usage_analysis"]),
        "by_category": by_category,
    }

    return {
        **state,
        "ghost_subscriptions": ghosts,
        "active_subscriptions": actives,
        "cost_summary": cost_summary,
    }


# ─── Node 4: Gemini Tavsiye ───────────────────────────────────
ADVICE_PROMPT = """Sen bir kisisel finans danismanisin. Kullanicinin abonelik durumunu analiz et ve somut tavsiyeler ver.

## Abonelik Ozeti:
- Toplam abonelik sayisi: {total_count}
- Aktif kullanilanlar: {active_count}
- Hayalet (kullanilmayan): {ghost_count}
- Aylik toplam maliyet: {total_monthly} TL
- Aylik israf (hayaletler): {ghost_monthly} TL
- Yillik tasarruf potansiyeli: {potential_savings_yearly} TL
- Simdiye kadar israf edilen: {total_wasted_so_far} TL

## Hayalet Abonelikler (iptal edilmeli):
{ghost_details}

## Aktif Abonelikler:
{active_details}

## Kategori Bazli Aylik Harcama:
{category_breakdown}

GOREVLERIN:
1. Her hayalet abonelik icin iptal tavsiyesi ver ve sebebini acikla
2. Ucretsiz alternatifler oner (varsa)
3. Aktif abonelikler icin optimizasyon onerileri sun (daha ucuz plan var mi?)
4. Genel bir tasarruf plani olustur
5. Motivasyonel bir kapanış yap (ne kadar tasarruf edebilecegini vurgula, Yatırımdan bahset,faiz karıştırma)

KURALLAR:
- Turkce yaz
- Samimi ama profesyonel ol
- Rakamlar ve yüzdeler kullan
- Her oneri somut ve uygulanabilir olsun
- Emoji kullan (okunabilirligi arttirir)"""


def generate_advice_node(state: SubscriptionSlayerState) -> SubscriptionSlayerState:
    """Gemini ile kisisellestirilmis iptal/optimizasyon tavsiyesi uretir"""
    if state.get("error"):
        return state

    try:
        time.sleep(2)

        ghost_details = ""
        for g in state["ghost_subscriptions"]:
            ghost_details += (
                f"- {g['name']}: {g['monthly_cost']} TL/ay, "
                f"{g['months_active']} aydır aktif (kullanilmiyor olabilir), "
                f"kategori: {g['category_label']}, "
                f"simdiye kadar odenen: {g['total_spent']} TL\n"
            )
        if not ghost_details:
            ghost_details = "Hayalet abonelik bulunamadi!"

        active_details = ""
        for a in state["active_subscriptions"]:
            active_details += (
                f"- {a['name']}: {a['monthly_cost']} TL/ay, "
                f"{a['months_active']} aydır aktif, "
                f"kategori: {a['category_label']}\n"
            )

        cs = state["cost_summary"]
        category_breakdown = "\n".join(
            f"- {cat}: {amount} TL/ay" for cat, amount in cs["by_category"].items()
        )

        prompt = ADVICE_PROMPT.format(
            total_count=cs["total_count"],
            active_count=cs["active_count"],
            ghost_count=cs["ghost_count"],
            total_monthly=cs["total_monthly"],
            ghost_monthly=cs["ghost_monthly"],
            potential_savings_yearly=cs["potential_savings_yearly"],
            total_wasted_so_far=cs["total_wasted_so_far"],
            ghost_details=ghost_details,
            active_details=active_details,
            category_breakdown=category_breakdown,
        )

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )
        advice = response.text

        # Hayalet abonelikler icin iptal linklerini hazirla
        ghost_items = []
        for g in state["ghost_subscriptions"]:
            cancel_url = g.get("cancel_url", "")

            # cancel_url yoksa web'de ara
            if not cancel_url:
                try:
                    search_result = search_web(
                        f"{g['name']} cancel subscription link",
                        max_results=1
                    )
                    if search_result and search_result.get("results"):
                        cancel_url = search_result["results"][0].get("url", "")
                except Exception:
                    cancel_url = ""

            ghost_items.append({
                "name": g["name"],
                "monthly_cost": g["monthly_cost"],
                "months_active": g["months_active"],
                "category": g["category_label"],
                "total_spent": g["total_spent"],
                "status": g["usage_status"],
                "cancel_url": cancel_url,
            })

        report = {
            "summary": {
                "total_subscriptions": cs["total_count"],
                "ghost_count": cs["ghost_count"],
                "active_count": cs["active_count"],
                "monthly_cost": cs["total_monthly"],
                "monthly_waste": cs["ghost_monthly"],
                "yearly_savings_potential": cs["potential_savings_yearly"],
                "total_wasted": cs["total_wasted_so_far"],
            },
            "ghosts": ghost_items,
            "actives": [
                {
                    "name": a["name"],
                    "monthly_cost": a["monthly_cost"],
                    "months_active": a["months_active"],
                    "category": a["category_label"],
                }
                for a in state["active_subscriptions"]
            ],
            "by_category": cs["by_category"],
            "advice": advice,
        }

        return {**state, "advice": advice, "report": report}

    except Exception as e:
        return {**state, "error": f"Gemini tavsiye hatasi: {str(e)}"}


# ─── Graph Olustur ────────────────────────────────────────────
def build_subscription_slayer():
    """Subscription Slayer graph'ini olusturur"""
    graph = StateGraph(SubscriptionSlayerState)

    graph.add_node("data_load", data_load_node)
    graph.add_node("analyze_usage", analyze_usage_node)
    graph.add_node("detect_ghosts", detect_ghosts_node)
    graph.add_node("generate_advice", generate_advice_node)

    graph.add_edge(START, "data_load")
    graph.add_edge("data_load", "analyze_usage")
    graph.add_edge("analyze_usage", "detect_ghosts")
    graph.add_edge("detect_ghosts", "generate_advice")
    graph.add_edge("generate_advice", END)

    return graph.compile()


# Graph instance
subscription_slayer = build_subscription_slayer()


def run_subscription_slayer(custom_subscriptions: list[dict] | None = None) -> dict:
    """Subscription Slayer'i calistirir"""
    result = subscription_slayer.invoke({
        "subscriptions": custom_subscriptions or [],
        "usage_analysis": [],
        "ghost_subscriptions": [],
        "active_subscriptions": [],
        "cost_summary": {},
        "advice": "",
        "report": {},
        "error": "",
    })

    if result["error"]:
        return {
            "error": result["error"],
            "report": result.get("report", {}),
        }

    return {
        "error": "",
        "report": result["report"],
        "advice": result["advice"],
        "cost_summary": result["cost_summary"],
        "ghost_count": result["cost_summary"].get("ghost_count", 0),
        "potential_savings": result["cost_summary"].get("potential_savings_yearly", 0),
    }


# ─── Test ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print("  Subscription Slayer Agent - Test")
    print("=" * 60)

    print("\nAbonelikler taraniyor...")
    result = run_subscription_slayer()

    if result.get("error"):
        print(f"\nHata: {result['error']}")
    else:
        report = result["report"]
        summary = report["summary"]

        print(f"\n--- ABONELIK OZETI ---")
        print(f"Toplam abonelik: {summary['total_subscriptions']}")
        print(f"Aktif kullanilanlar: {summary['active_count']}")
        print(f"Hayalet abonelikler: {summary['ghost_count']}")
        print(f"Aylik toplam: {summary['monthly_cost']} TL")
        print(f"Aylik israf: {summary['monthly_waste']} TL")
        print(f"Yillik tasarruf potansiyeli: {summary['yearly_savings_potential']} TL")

        print(f"\n--- HAYALET ABONELIKLER ---")
        for g in report["ghosts"]:
            print(f"  {g['name']}: {g['monthly_cost']} TL/ay ({g['months_active']} aydir aktif - riskli)")

        print(f"\n--- GEMINI TAVSIYESI ---")
        print(result["advice"][:800])

    print("\n" + "=" * 60)
    print("Test tamamlandi!")
