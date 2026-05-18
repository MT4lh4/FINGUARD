"""
FinGuard AI - FastAPI Backend
==============================
Ana API endpoint'leri.
Tüm ajanlar, ayarlar, sohbet geçmişi ve bütçe yönetimi burada.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import sys
import os
from pathlib import Path

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from orchestrator import run_orchestrator
from agents.subscription_slayer import run_subscription_slayer
from agents.impulse_guard import run_impulse_guard
from agents.market_analyst import run_market_analyst
from config import settings, AVAILABLE_MODELS, DEFAULT_MODEL, CATEGORIES
from data.budget_db import (
    set_budget_limit, get_all_budget_limits, delete_budget_limit,
    save_chat, get_chat_history, clear_chat_history,
    set_setting, get_setting, get_all_settings,
    get_monthly_history, get_lifetime_balance,
)


# ─── App ───────────────────────────────────────────────────────
# Dedicated thread pool — agent fonksiyonları CPU/IO blocking olduğu için
# event loop'u bloke etmemek için buraya alınıyor.
_executor = ThreadPoolExecutor(max_workers=4)

app = FastAPI(
    title="FinGuard AI",
    description="Yapay zeka destekli finansal asistan platformu",
    version="0.2.0",
)

# CORS - Frontend ve Chrome Extension için
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Modeller (Pydantic) ─────────────────────────────────────
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    intent: str
    response: str
    agent: str
    decision: Optional[str] = None
    notion_url: Optional[str] = None
    budget_data: Optional[dict] = None
    subscription_data: Optional[dict] = None
    impulse_data: Optional[dict] = None

class ProductAnalysisRequest(BaseModel):
    name: str = "Bilinmeyen Ürün"
    price: float = 0.0
    site: str = ""
    url: str = ""

class SettingUpdate(BaseModel):
    key: str
    value: str

class EnvKeyUpdate(BaseModel):
    key: str
    value: str

class BudgetLimitUpdate(BaseModel):
    category: str
    limit: float

class MarketRequest(BaseModel):
    query: str


# ─── Frontend Serving ─────────────────────────────────────────
@app.get("/")
async def root():
    """Ana arayüzü sunar"""
    frontend_path = Path(__file__).parent.parent / "frontend" / "index.html"
    return FileResponse(str(frontend_path))

frontend_dir = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


# ─── Health ───────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """Backend ve DB sağlık kontrolü"""
    from data.budget_db import get_connection
    from datetime import datetime as _dt
    db_ok = False
    try:
        conn = get_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "version": "2.0.0",
        "timestamp": _dt.now().isoformat(),
        "model": settings.GEMINI_MODEL,
    }


@app.get("/api/categories")
async def api_get_categories():
    """Frontend'in kullandığı canonical kategori listesini döndürür."""
    return [
        {"id": c["id"], "label": c["label"], "icon": c["icon"]}
        for c in CATEGORIES
    ]


# ─── Budget Log (Direct) ───────────────────────────────────────────
@app.post("/api/budget/log")
async def budget_log(req: ChatRequest):
    """
    Budget Logger agent’ını doğrudan çalıştırır.
    Frontend logBudget() bu endpoint’i önce dener, fallback /chat’e düşer.
    """
    try:
        from agents.budget_logger import run_budget_logger
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_executor, run_budget_logger, req.message)
        return {
            "response":        result.get("response", ""),
            "parsed_expenses": result.get("parsed_expenses", []),
            "monthly_summary": result.get("monthly_summary", {}),
            "error":           result.get("error", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Budget log hatası: {str(e)}")


# ─── Chat ─────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Ana chat endpoint'i.
    Kullanıcı mesajını orkestratöre gönderir,
    doğru agent'a yönlendirir, yanıtı sohbet geçmişine kaydeder.
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Mesaj boş olamaz")

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_executor, run_orchestrator, request.message)

        agent = result["agent_outputs"].get("agent", "unknown")
        decision = result["agent_outputs"].get("decision")
        notion_url = result["agent_outputs"].get("notion_url")

        # Sohbet geçmişine kaydet
        save_chat(
            user_message=request.message,
            ai_response=result["response"],
            agent=agent,
            intent=result["intent"],
            decision=decision,
            notion_url=notion_url,
        )

        return ChatResponse(
            intent=result["intent"],
            response=result["response"],
            agent=agent,
            decision=decision,
            notion_url=notion_url,
            budget_data=result["agent_outputs"].get("budget_data"),
            subscription_data=result["agent_outputs"].get("subscription_data"),
            impulse_data=result["agent_outputs"].get("impulse_data"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Orkestratör hatası: {str(e)}")


# ─── Chat History ─────────────────────────────────────────────
@app.get("/api/chat-history")
async def api_chat_history(limit: int = 50):
    """Son N sohbeti döndürür."""
    return get_chat_history(limit=limit)

@app.delete("/api/chat-history")
async def api_clear_chat_history():
    """Tüm sohbet geçmişini temizler."""
    count = clear_chat_history()
    return {"cleared": count}


# ─── Settings (Model & App Config) ───────────────────────────
@app.get("/api/settings")
async def api_get_settings():
    """Tüm uygulama ayarlarını döndürür (model, maskelenmiş key'ler)."""
    return {
        "model": settings.GEMINI_MODEL,
        "available_models": AVAILABLE_MODELS,
        "api_keys": settings.get_masked_keys(),
        "api_status": settings.validate(),
        "db_settings": get_all_settings(),
    }

@app.post("/api/settings")
async def api_update_setting(update: SettingUpdate):
    """DB'deki bir ayarı günceller (model seçimi vb.)."""
    set_setting(update.key, update.value)
    return {"ok": True, "key": update.key, "value": update.value}

@app.get("/api/settings/models")
async def api_get_models():
    """Mevcut model listesini döndürür."""
    return {
        "models": AVAILABLE_MODELS,
        "current": settings.GEMINI_MODEL,
    }

@app.post("/api/settings/env")
async def api_update_env_key(update: EnvKeyUpdate):
    """
    .env dosyasına bir API key yazar.
    Sadece bilinen anahtarları kabul eder (güvenlik).
    """
    try:
        settings.set_env_key(update.key, update.value)
        return {
            "ok": True,
            "key": update.key,
            "masked": settings.get_masked_keys().get(update.key, ""),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Budget Limits ────────────────────────────────────────────
@app.get("/api/budget-limits")
async def api_get_budget_limits():
    """Tüm bütçe limitlerini döndürür."""
    return get_all_budget_limits()

@app.post("/api/budget-limits")
async def api_set_budget_limit(update: BudgetLimitUpdate):
    """Bir bütçe limiti ayarlar/günceller."""
    set_budget_limit(update.category.lower().strip(), update.limit)
    return {"ok": True, "category": update.category, "limit": update.limit}

@app.delete("/api/budget-limits/{category}")
async def api_delete_budget_limit(category: str):
    """Bir bütçe limitini siler."""
    deleted = delete_budget_limit(category)
    if not deleted:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı")
    return {"ok": True, "deleted": category}


@app.get("/api/budget/summary")
async def api_budget_summary(month: int = None, year: int = None):
    """İstenen aya ait harcama özeti döndürür. Parametre verilmezse bu ayı döndürür."""
    from data.budget_db import get_monthly_summary
    from datetime import datetime
    now = datetime.now()
    return get_monthly_summary(
        month=month or now.month,
        year=year or now.year
    )


@app.get("/api/budget/available-months")
async def api_available_months():
    """DB'de harcama kaydı olan tüm ay-yıl çiftlerini listeler."""
    from data.budget_db import get_connection
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT strftime('%Y-%m', date) as month FROM expenses ORDER BY month DESC"
    ).fetchall()
    conn.close()
    return [r["month"] for r in rows]


@app.get("/api/budget/history")
async def api_budget_history():
    """
    Harcama kaydı olan tüm ayların özet listesini döndürür.
    Her ay için o aya ait doğru limit ve kâr/zarar bilgisi içerir.
    """
    months = get_monthly_history()
    lifetime = get_lifetime_balance()
    return {
        "months": months,
        "lifetime_balance": lifetime,
    }


# ─── Market Analyst Direct ──────────────────────────────
@app.post("/api/market/analyze")
async def api_market_analyze(req: MarketRequest):
    """
    Market Analyst agent'ını doğrudan çalıştırır.
    Yapılandırılmış kart verisi döndürür.
    """
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_executor, run_market_analyst, req.query)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Market analiz hatası: {str(e)}")


# ─── Product Analysis (Chrome Extension) ─────────────────────
@app.post("/analyze-product")
async def analyze_product(product: ProductAnalysisRequest):
    """
    Chrome Extension'dan gelen ürün bilgisini analiz eder.
    Impulse Guard agent'ını doğrudan tetikler.
    Alternatif ürün verilerini de döndürür.
    """
    try:
        loop = asyncio.get_event_loop()
        import functools
        result = await loop.run_in_executor(
            _executor,
            functools.partial(run_impulse_guard, product.name, product.price)
        )

        return {
            "decision":      result.get("decision", "BEKLE"),
            "message":       result.get("intervention", "Analiz yapılamadı."),
            "budget_status": result.get("budget_status", {}),
            "category":      result.get("category", ""),
            "alternatives":  result.get("alternatives", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ürün analiz hatası: {str(e)}")


# ─── Subscriptions ────────────────────────────────────────────
@app.get("/subscriptions")
async def scan_subscriptions():
    """Kullanicinin aboneliklerini tarar, hayalet abonelikleri tespit eder."""
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_executor, run_subscription_slayer)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        return result["report"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Abonelik tarama hatasi: {str(e)}")

@app.post("/subscriptions/analyze")
async def analyze_custom_subscriptions(subscriptions: list[dict]):
    """Kullanicinin manuel girdigi abonelikleri analiz eder."""
    if not subscriptions:
        raise HTTPException(status_code=400, detail="Abonelik listesi bos olamaz")

    try:
        import functools
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor,
            functools.partial(run_subscription_slayer, custom_subscriptions=subscriptions)
        )
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        return result["report"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analiz hatasi: {str(e)}")


@app.on_event("shutdown")
def shutdown_executor():
    """Uygulama kapatılırken thread pool'ı temiz kapat."""
    _executor.shutdown(wait=False)
