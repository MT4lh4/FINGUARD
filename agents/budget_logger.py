"""
Budget Logger Agent
===================
Doğal dille yazılan harcamaları otomatik kategorize edip veritabanına kaydeden agent.

Akış: parse_expense → categorize → save_to_db → generate_summary → END

Kullanım:
    result = run_budget_logger("Bugün 150 TL markete harcadım, 45 TL de kahve için")
"""

import sys
import time
import json
import re
from pathlib import Path
from typing import TypedDict
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from google import genai
from langgraph.graph import StateGraph, START, END
from config import settings, CATEGORIES
from data.budget_db import add_expense, get_monthly_summary, get_limit_for_month


# ─── State ─────────────────────────────────────────────────────
class BudgetLoggerState(TypedDict):
    user_input: str             # Kullanıcının doğal dil girdisi
    parsed_expenses: list[dict] # Ayrıştırılmış harcamalar
    saved_ids: list[int]        # Veritabanına kaydedilen ID'ler
    monthly_summary: dict       # Aylık özet
    response: str               # Kullanıcıya gösterilecek yanıt
    error: str


# ─── Gemini Client ─────────────────────────────────────────────
client = genai.Client(api_key=settings.GEMINI_API_KEY)


# ─── Node 1: Doğal Dil → Yapılandırılmış Veri ─────────────────
def build_parse_prompt(user_input: str, today: str) -> str:
    """CATEGORIES config'inden dinamik olarak Gemini prompt'u üretir."""
    cat_lines = "\n".join(
        f'- {c["id"]}: {c["label"]} — '
        + (", ".join(c["keywords"][:6]) if c["keywords"] else "diğer her şey")
        for c in CATEGORIES
    )
    cat_ids = ", ".join(c["id"] for c in CATEGORIES)

    examples = []
    for c in CATEGORIES:
        if c["keywords"]:
            examples.append(f'- "{c["keywords"][0]}" → {c["id"]}')
    example_lines = "\n".join(examples[:10])

    return f"""Sen bir harcama ayrıştırıcısısın. Kullanıcının doğal dilde yazdığı metni JSON'a çevir.

İstek iki türlü olabilir:
1. Harcama kaydı: "Bugün 150 TL markete harcadım"
2. Bütçe limiti: "Market bütçemi 5000 TL yap"

Kullanıcı girdisi: "{user_input}"
Bugünün tarihi: {today}

Her JSON objesi şu alanları içermeli:
- action: "log_expense" veya "set_limit"
- amount: Tutar (sayı, bulunamazsa 0)
- currency: "TRY"
- category: Aşağıdaki listeden SADECE id değerini yaz
- description: Kısa açıklama (sadece log_expense)
- date: YYYY-MM-DD (sadece log_expense)

KATEGORİ LİSTESİ (sadece id kullan):
{cat_lines}

ÖRNEKLER:
{example_lines}

KURALLAR:
- category alanına SADECE şunlardan birini yaz: {cat_ids}
- Sadece JSON dizisi döndür
- Markdown kod bloğu KULLANMA

Örnek çıktı:
[{{"action": "log_expense", "amount": 150, "currency": "TRY", "category": "market", "description": "Market alışverişi", "date": "{today}"}}]"""


def parse_expense_node(state: BudgetLoggerState) -> BudgetLoggerState:
    """Doğal dil girdisini yapılandırılmış harcama verisine çevirir"""
    if state.get("error"):
        return state

    try:
        time.sleep(2)  # Rate limit

        prompt = build_parse_prompt(
            user_input=state["user_input"],
            today=datetime.now().strftime("%Y-%m-%d")
        )

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )

        text = response.text.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(text)

        if not isinstance(parsed, list):
            parsed = [parsed]

        return {**state, "parsed_expenses": parsed}

    except Exception as e:
        return {**state, "error": f"Harcama ayrıştırma hatası: {str(e)}"}


# ─── Node 2: Veritabanına Kaydet ──────────────────────────────
def save_to_db_node(state: BudgetLoggerState) -> BudgetLoggerState:
    """Ayrıştırılmış harcamaları SQLite veritabanına kaydeder"""
    if state.get("error"):
        return state

    saved_ids = []
    errors = []
    today = datetime.now().strftime("%Y-%m-%d")

    for item in list(state["parsed_expenses"]):
        try:
            if item.get("action") == "set_limit":
                from data.budget_db import set_budget_limit
                set_budget_limit(
                    category=item.get("category", "diger"),
                    limit=float(item.get("amount", 0))
                )
            else:
                expense_id = add_expense(
                    amount=float(item.get("amount", 0)),
                    category=item.get("category", "diger"),
                    description=item.get("description", ""),
                    currency=item.get("currency", "TRY"),
                    date=item.get("date", today),
                )
                saved_ids.append(expense_id)
        except Exception as e:
            desc = item.get("description", item.get("category", "?"))
            errors.append(f"{desc}: {str(e)}")
            state["parsed_expenses"].remove(item)

    return {**state, "saved_ids": saved_ids, "error": "; ".join(errors)}


# ─── Node 3: Aylık Özet ───────────────────────────────────────
def generate_summary_node(state: BudgetLoggerState) -> BudgetLoggerState:
    """Aylık harcama özeti oluşturur ve kullanıcıya güzel bir yanıt hazırlar"""
    if state.get("error"):
        return state

    now = datetime.now()
    summary = get_monthly_summary(month=now.month, year=now.year)

    # Güzel bir yanıt oluştur
    lines = ["✅ **İşlem başarılı!**\n"]

    for i, item in enumerate(state["parsed_expenses"]):
        cat_emoji = {
            "market": "🛒", "restoran": "☕", "ulasim": "🚗",
            "fatura": "📄", "eglence": "🎬", "giyim": "👕",
            "saglik": "💊", "egitim": "📚", "elektronik": "💻",
            "kira": "🏠", "diger": "📌"
        }
        emoji = cat_emoji.get(item.get("category", ""), "📌")
        
        if item.get("action") == "set_limit":
            lines.append(f"  {emoji} Bütçe Limiti Güncellendi: {item.get('category', '').capitalize()} kategorisi için {item.get('amount', 0)} {item.get('currency', 'TRY')}")
        else:
            lines.append(
                f"  {emoji} {item.get('category', 'diger').capitalize()}: "
                f"{item.get('amount', 0)} {item.get('currency', 'TRY')}"
                f" — {item.get('description', '')}"
            )

    lines.append(f"\n📊 **Bu Ay Özeti ({now.strftime('%B %Y')}):**")
    lines.append(f"  💰 Toplam harcama: {summary['total']} TL")
    lines.append(f"  📝 İşlem sayısı: {summary['transaction_count']}")

    if summary["by_category"]:
        lines.append(f"  🏆 En çok harcanan: {summary['top_category'].capitalize()} ({summary['top_category_amount']} TL)")

    if summary["prev_month_total"] > 0:
        arrow = "📈" if summary["change_percent"] > 0 else "📉"
        lines.append(f"  {arrow} Geçen aya göre: %{summary['change_percent']:+.1f}")

    # Kategori bazlı limit & doluluk bilgisi
    if summary["by_category"]:
        lines.append("\n  **Kategori Limitleri:**")
        for cat, amount in summary["by_category"].items():
            limit = get_limit_for_month(cat, now.month, now.year)
            pct = (amount / limit * 100) if limit > 0 else 0
            status = "🔴" if pct >= 100 else ("🟡" if pct >= 80 else "🟢")
            lines.append(f"    {status} {cat.capitalize()}: {amount} / {limit} TL (%{pct:.0f})")

    response_text = "\n".join(lines)

    return {**state, "monthly_summary": summary, "response": response_text}


# ─── Graph Oluştur ────────────────────────────────────────────
def build_budget_logger():
    """Budget Logger graph'ını oluşturur"""
    graph = StateGraph(BudgetLoggerState)

    graph.add_node("parse_expense", parse_expense_node)
    graph.add_node("save_to_db", save_to_db_node)
    graph.add_node("generate_summary", generate_summary_node)

    graph.add_edge(START, "parse_expense")
    graph.add_edge("parse_expense", "save_to_db")
    graph.add_edge("save_to_db", "generate_summary")
    graph.add_edge("generate_summary", END)

    return graph.compile()


# Graph instance
budget_logger = build_budget_logger()


def run_budget_logger(user_input: str) -> dict:
    """Budget Logger'ı çalıştırır"""
    result = budget_logger.invoke({
        "user_input": user_input,
        "parsed_expenses": [],
        "saved_ids": [],
        "monthly_summary": {},
        "response": "",
        "error": "",
    })

    if result["error"]:
        return {"error": result["error"], "response": result.get("response", "")}

    return {
        "error": "",
        "response": result["response"],
        "parsed_expenses": result["parsed_expenses"],
        "saved_ids": result["saved_ids"],
        "monthly_summary": result["monthly_summary"],
    }


# ─── Test ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    os.environ["PYTHONIOENCODING"] = "utf-8"
    sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print("  🧾 Budget Logger Agent - Test")
    print("=" * 60)

    test_inputs = [
        "Bugün 150 TL markete harcadım, 45 TL de kahve için verdim",
        "Elektrik faturası 320 TL ödedim",
    ]

    for i, text in enumerate(test_inputs):
        print(f"\n--- Test {i+1} ---")
        print(f"📝 Girdi: \"{text}\"")
        print("⏳ İşleniyor...\n")

        result = run_budget_logger(text)

        if result.get("error"):
            print(f"⚠️ Hata: {result['error']}")
        else:
            print(result["response"])

        if i < len(test_inputs) - 1:
            print("\n⏳ Rate limit bekleniyor...")
            time.sleep(5)

    print("\n" + "=" * 60)
    print("✅ Budget Logger testi tamamlandı!")
