"""
Gün 8 - Uçtan Uca Entegrasyon Testi
=====================================
4 ana senaryo ile tüm agentların orkestratör üzerinden çalışmasını test eder.
"""
import sys
import os
import time

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from orchestrator import run_orchestrator

SCENARIOS = [
    {
        "name": "Senaryo 1: Budget Logger",
        "input": "Bugün 250 TL markete harcadım, 80 TL de benzin aldım",
        "expected_agent": "budget_logger",
    },
    {
        "name": "Senaryo 2: Subscription Slayer",
        "input": "Aboneliklerimi kontrol et, gereksiz olanları iptal etmem lazım",
        "expected_agent": "subscription_slayer",
    },
    {
        "name": "Senaryo 3: Impulse Guard (Budget Logger DB ile entegre)",
        "input": "3500 TL'lik bir gaming kulaklık almayı düşünüyorum, almalı mıyım?",
        "expected_agent": "impulse_guard",
    },
    {
        "name": "Senaryo 4: Genel Sohbet",
        "input": "Merhaba FinGuard, bana nasıl yardımcı olabilirsin?",
        "expected_agent": "general",
    },
]

print("=" * 70)
print("  🔗 Gün 8 - Uçtan Uca Entegrasyon Testi")
print("=" * 70)

passed = 0
failed = 0

for i, scenario in enumerate(SCENARIOS):
    if i > 0:
        wait = 8
        print(f"\n⏳ API rate limit bekleniyor ({wait}s)...")
        time.sleep(wait)

    print(f"\n{'─' * 70}")
    print(f"📋 {scenario['name']}")
    print(f"📝 Girdi: \"{scenario['input']}\"")
    print(f"🎯 Beklenen Agent: {scenario['expected_agent']}")
    print("⏳ Çalışıyor...\n")

    try:
        start_time = time.time()
        result = run_orchestrator(scenario["input"])
        elapsed = round(time.time() - start_time, 1)

        actual_agent = result["agent_outputs"].get("agent", "unknown")
        intent = result["intent"]
        response_preview = result["response"][:300]

        correct = actual_agent == scenario["expected_agent"]

        status = "✅ BAŞARILI" if correct else "⚠️ YANLIŞ AGENT"

        print(f"   {status}")
        print(f"   🎯 Intent: {intent}")
        print(f"   🤖 Agent: {actual_agent}")
        print(f"   ⏱️ Süre: {elapsed}s")
        print(f"   📤 Yanıt:\n   {response_preview}...")

        if correct:
            passed += 1
        else:
            failed += 1

    except Exception as e:
        print(f"   ❌ HATA: {str(e)}")
        failed += 1

print(f"\n{'=' * 70}")
print(f"  📊 SONUÇ: {passed}/{passed + failed} senaryo başarılı")
if failed == 0:
    print("  🎉 Tüm entegrasyon testleri geçti!")
else:
    print(f"  ⚠️ {failed} senaryo başarısız")
print("=" * 70)
