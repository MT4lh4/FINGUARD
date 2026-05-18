"""
FinGuard AI - Orkestratör Agent
================================
Kullanıcıdan gelen isteği analiz eder, hangi agent'ın devreye
gireceğine karar verir, agentlar arası veri akışını yönetir.

Langgraph ile multi-agent orkestrasyon.
"""

import re
import time
from typing import TypedDict
from google import genai
from langgraph.graph import StateGraph, START, END
from config import settings
from agents.market_analyst import run_market_analyst
from agents.subscription_slayer import run_subscription_slayer
from agents.impulse_guard import run_impulse_guard
from agents.budget_logger import run_budget_logger


# ─── State Tanımı ─────────────────────────────────────────────
class AgentState(TypedDict):
    """Orkestratör state'i - tüm agentlar arası paylaşılan durum"""
    user_input: str
    intent: str
    agent_outputs: dict
    final_response: str


# ─── Gemini Client ─────────────────────────────────────────────
client = genai.Client(api_key=settings.GEMINI_API_KEY)


# ─── Intent Classification ────────────────────────────────────
INTENT_PROMPT = """Sen bir finansal asistan orkestratörüsün. Kullanıcının isteğini analiz et ve hangi kategoriye düştüğünü belirle.

Kategoriler:
- "market_analysis": Piyasa araştırması, ürün/pazar analizi, trend analizi
- "subscription_check": Abonelik kontrolü, hayalet abonelik, iptal tavsiyesi
- "impulse_guard": Ürün satın alma niyeti, harcama danışmanlığı, alışveriş koçluğu
- "budget_log": Harcama kaydı, bütçe takibi, para harcama bildirimi
- "general": Yukarıdakilere uymayan genel sorular

Kullanıcı mesajı: "{user_input}"

SADECE kategori adını döndür, başka bir şey yazma."""

GENERAL_RESPONSE_PROMPT = """Sen FinGuard AI finansal asistanısın. Kullanıcıya yardımcı ol.

Şu özelliklerin var:
1. Piyasa/ürün analizi yapabilirsin (Market Analyst)
2. Abonelikleri kontrol edebilirsin (Subscription Slayer)
3. Alışveriş kararlarında koçluk yapabilirsin (Impulse Guard)
4. Harcamaları kaydedebilirsin (Budget Logger)

Kullanıcı mesajı: "{user_input}"

Kısa ve samimi bir şekilde yanıtla. Yukarıdaki özelliklerinden bahsedebilirsin."""


# ─── Node Fonksiyonları ───────────────────────────────────────
def classify_node(state: AgentState) -> AgentState:
    """Kullanıcı isteğini sınıflandırır"""
    user_input = state["user_input"].strip()
    if not user_input:
        return {**state, "intent": "general"}

    try:
        time.sleep(1)  # Rate limit koruması
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=INTENT_PROMPT.format(user_input=user_input)
        )
        intent = response.text.strip().lower().strip('"')

        valid_intents = ["market_analysis", "subscription_check", "impulse_guard", "budget_log", "general"]
        if intent not in valid_intents:
            intent = "general"

        return {**state, "intent": intent}
    except Exception as e:
        # API hatası olursa general'e düş, crash olmasın
        return {**state, "intent": "general"}


def market_analyst_node(state: AgentState) -> AgentState:
    """Market Analyst agent'ını çalıştırır"""
    result = run_market_analyst(state["user_input"])

    response = f"📊 **Pazar Analizi Tamamlandı**\n\n{result['analysis'][:500]}"
    if result["notion_url"]:
        response += f"\n\n📝 Tam rapor Notion'da: {result['notion_url']}"
    if result["error"]:
        response += f"\n\n⚠️ Not: {result['error']}"

    return {
        **state,
        "agent_outputs": {
            "agent": "market_analyst",
            "status": "completed",
            "notion_url": result.get("notion_url", ""),
            "sources_count": result.get("sources_count", 0),
        },
        "final_response": response
    }


def subscription_slayer_node(state: AgentState) -> AgentState:
    """Subscription Slayer agent'ini calistirir"""
    result = run_subscription_slayer()

    if result.get("error"):
        return {
            **state,
            "agent_outputs": {"agent": "subscription_slayer", "status": "error"},
            "final_response": f"Abonelik taramasi sirasinda hata: {result['error']}",
        }

    report = result["report"]
    summary = report["summary"]

    ghost_list = ""
    for g in report["ghosts"]:
        ghost_list += f"  - {g['name']}: {g['monthly_cost']} TL/ay ({g['months_active']} aydir aktif - hayalet risk)\n"

    response = (
        f"ABONELIK TARAMA SONUCU\n\n"
        f"Toplam: {summary['total_subscriptions']} abonelik | "
        f"Aktif: {summary['active_count']} | "
        f"Hayalet: {summary['ghost_count']}\n"
        f"Aylik maliyet: {summary['monthly_cost']} TL | "
        f"Aylik israf: {summary['monthly_waste']} TL\n"
        f"Yillik tasarruf potansiyeli: {summary['yearly_savings_potential']} TL\n\n"
    )

    if ghost_list:
        response += f"HAYALET ABONELIKLER:\n{ghost_list}\n"

    response += f"\nTAVSIYELER:\n{result['advice'][:1500]}"

    return {
        **state,
        "agent_outputs": {
            "agent": "subscription_slayer",
            "status": "completed",
            "ghost_count": summary["ghost_count"],
            "monthly_waste": summary["monthly_waste"],
            "yearly_savings": summary["yearly_savings_potential"],
            "subscription_data": {
                "summary": report["summary"],
                "ghosts": report["ghosts"],
                "actives": report["actives"],
                "by_category": report["by_category"],
                "advice": result.get("advice", ""),
            },
        },
        "final_response": response,
    }


def _extract_price_from_text(text: str) -> float:
    """Doğal dilden TL cinsinden fiyat çıkarır."""
    match = re.search(
        r'(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?)\s*(?:TL|₺|lira|tl)',
        text, re.IGNORECASE
    )
    if match:
        raw = match.group(1).replace(".", "").replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            pass
    return 0.0


def impulse_guard_node(state: AgentState) -> AgentState:
    """Impulse Guard agent'ini calistirir"""
    price = _extract_price_from_text(state["user_input"])
    result = run_impulse_guard(state["user_input"], price=price)

    if result.get("error"):
        return {
            **state,
            "agent_outputs": {"agent": "impulse_guard", "status": "error"},
            "final_response": f"Urun analizi sirasinda hata: {result['error']}",
        }

    response = (
        f"🛑 **KARAR: {result['decision']}**\n"
        f"Kategori: {result['category']} | Kalan Butce: {result['budget_status']['kalan']} TL\n\n"
        f"{result['intervention']}"
    )

    return {
        **state,
        "agent_outputs": {
            "agent": "impulse_guard",
            "status": "completed",
            "decision": result["decision"],
            "impulse_data": {
                "product": result["product"],
                "category": result["category"],
                "decision": result["decision"],
                "intervention": result["intervention"],
                "budget_status": result["budget_status"],
            },
        },
        "final_response": response,
    }


def budget_logger_node(state: AgentState) -> AgentState:
    """Budget Logger agent'ini calistirir"""
    result = run_budget_logger(state["user_input"])

    if result.get("error"):
        return {
            **state,
            "agent_outputs": {"agent": "budget_logger", "status": "error"},
            "final_response": f"Harcama kaydi hatasi: {result['error']}",
        }

    return {
        **state,
        "agent_outputs": {
            "agent": "budget_logger",
            "status": "completed",
            "saved_count": len(result.get("saved_ids", [])),
            "budget_data": {
                "parsed_expenses": result.get("parsed_expenses", []),
                "monthly_summary": result.get("monthly_summary", {}),
            },
        },
        "final_response": result["response"],
    }


def general_response_node(state: AgentState) -> AgentState:
    """Genel sorulara Gemini ile yanıt verir"""
    time.sleep(1)  # Rate limit koruması
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=GENERAL_RESPONSE_PROMPT.format(user_input=state["user_input"])
    )
    return {
        **state,
        "agent_outputs": {"agent": "general"},
        "final_response": response.text
    }


# ─── Router ───────────────────────────────────────────────────
def route_by_intent(state: AgentState) -> str:
    """Intent'e göre doğru node'a yönlendirir"""
    routing = {
        "market_analysis": "market_analyst",
        "subscription_check": "subscription_slayer",
        "impulse_guard": "impulse_guard",
        "budget_log": "budget_logger",
        "general": "general_response",
    }
    return routing.get(state["intent"], "general_response")


# ─── Graph Oluştur ────────────────────────────────────────────
def build_orchestrator():
    """Orkestratör graph'ını oluşturur ve derler"""
    graph = StateGraph(AgentState)

    # Node'ları ekle
    graph.add_node("classify", classify_node)
    graph.add_node("market_analyst", market_analyst_node)
    graph.add_node("subscription_slayer", subscription_slayer_node)
    graph.add_node("impulse_guard", impulse_guard_node)
    graph.add_node("budget_logger", budget_logger_node)
    graph.add_node("general_response", general_response_node)

    # Akış: START → classify → (conditional routing) → END
    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", route_by_intent)
    graph.add_edge("market_analyst", END)
    graph.add_edge("subscription_slayer", END)
    graph.add_edge("impulse_guard", END)
    graph.add_edge("budget_logger", END)
    graph.add_edge("general_response", END)

    return graph.compile()


# Orkestratör instance'ı
orchestrator = build_orchestrator()


def run_orchestrator(user_input: str) -> dict:
    """Orkestratörü çalıştırır ve sonucu döndürür"""
    result = orchestrator.invoke({
        "user_input": user_input,
        "intent": "",
        "agent_outputs": {},
        "final_response": "",
    })
    return {
        "intent": result["intent"],
        "response": result["final_response"],
        "agent_outputs": result["agent_outputs"],
    }


# ─── Test ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    import os
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding='utf-8')

    test_inputs = [
        "Mekanik klavye pazarını analiz et",
        "Aboneliklerimi kontrol et",
        "2000 TL'lik kulaklık almayı düşünüyorum",
        "Bugün 150 TL markete harcadım",
        "Merhaba, nasılsın?",
    ]

    print("🧠 FinGuard AI - Orkestratör Tam Akış Testi")
    print("=" * 60)

    for i, inp in enumerate(test_inputs):
        if i > 0:
            time.sleep(13)  # Rate limit koruması (free tier: 5/dk)

        result = run_orchestrator(inp)
        print(f"\n📝 Girdi: \"{inp}\"")
        print(f"   🎯 Intent: {result['intent']}")
        print(f"   📤 Yanıt: {result['response'][:100]}...")
