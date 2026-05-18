"""
FinGuard AI - Langgraph Temel Test
====================================
Gun 1 kontrolu: Langgraph duzgun calisiyor mu?
Basit bir graph ile akis testi.
"""

import sys
import os
from pathlib import Path
from typing import TypedDict

# Windows encoding fix
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8')

# Proje kokunu path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph.graph import StateGraph, START, END


# ─── Basit State Tanımı ────────────────────────────────────────
class SimpleState(TypedDict):
    message: str
    processed: bool


# ─── Node Fonksiyonları ────────────────────────────────────────
def receive_input(state: SimpleState) -> SimpleState:
    """Kullanıcı girdisini alır"""
    print(f"📥 Girdi alındı: {state['message']}")
    return state


def process_message(state: SimpleState) -> SimpleState:
    """Mesajı işler"""
    processed_msg = f"[İşlendi] {state['message']}"
    print(f"⚙️ İşleniyor: {processed_msg}")
    return {"message": processed_msg, "processed": True}


def generate_response(state: SimpleState) -> SimpleState:
    """Yanıt üretir"""
    response = f"FinGuard AI yanıtı: {state['message']} ✅"
    print(f"📤 Yanıt: {response}")
    return {"message": response, "processed": True}


# ─── Graph Oluştur ─────────────────────────────────────────────
def build_simple_graph():
    """Basit bir Langgraph graph'ı oluşturur"""
    graph = StateGraph(SimpleState)

    # Node'ları ekle
    graph.add_node("receive", receive_input)
    graph.add_node("process", process_message)
    graph.add_node("respond", generate_response)

    # Kenarları ekle (akış sırası)
    graph.add_edge(START, "receive")
    graph.add_edge("receive", "process")
    graph.add_edge("process", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


# ─── Test ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🔗 Langgraph temel test başlıyor...")
    print("=" * 50)

    app = build_simple_graph()

    # Test çalıştır
    result = app.invoke({
        "message": "Mekanik klavye pazarını analiz et",
        "processed": False,
    })

    print("\n" + "=" * 50)
    print(f"🏁 Sonuç: {result}")
    print("✅ Langgraph başarıyla çalışıyor!")
