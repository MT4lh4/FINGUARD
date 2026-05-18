"""
Budget Logger - SQLite Veritabanı Katmanı
==========================================
Harcamaları kalıcı olarak kaydeder, günceller, siler.
v2.0: budget_limits tablosu dönem yönetimiyle güncellendi.
"""

import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "budget.db"


def get_connection():
    """Veritabanı bağlantısı döndürür, tablo yoksa oluşturur."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Tabloları oluştur (mevcutsa dokunma)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'TRY',
            category TEXT NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_message TEXT NOT NULL,
            ai_response TEXT NOT NULL,
            agent TEXT DEFAULT 'general',
            intent TEXT,
            decision TEXT,
            notion_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)

    # budget_limits: dönem yönetimli şema
    # Eski şemayı yeni şemaya migrate et (idempotent)
    _migrate_budget_limits(conn)

    conn.commit()
    return conn


def _migrate_budget_limits(conn: sqlite3.Connection):
    """
    Eski tek-satır budget_limits şemasını dönem yönetimli yeni şemaya geçirir.
    Her çalıştırmada güvenle tekrarlanabilir (idempotent).
    """
    # Yeni şemada 'valid_from' kolonu var mı kontrol et
    cols = [row[1] for row in conn.execute("PRAGMA table_info(budget_limits)").fetchall()]

    if "valid_from" not in cols:
        # Eski veriler varsa al
        old_rows = []
        if "budget_limits" in [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_limits'"
        ).fetchall()]:
            try:
                old_rows = conn.execute("SELECT category, monthly_limit FROM budget_limits").fetchall()
            except Exception:
                pass

        # Eski tabloyu sil
        conn.execute("DROP TABLE IF EXISTS budget_limits")

        # Yeni şema
        conn.execute("""
            CREATE TABLE budget_limits (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                category      TEXT    NOT NULL,
                monthly_limit REAL    NOT NULL,
                valid_from    DATE    NOT NULL,
                valid_to      DATE,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_budget_limits_category ON budget_limits(category)"
        )

        # Eski kayıtları yeni şemaya taşı (valid_from = 2026-01-01, aktif)
        today = datetime.now().strftime("%Y-%m-%d")
        for row in old_rows:
            conn.execute(
                "INSERT INTO budget_limits (category, monthly_limit, valid_from) VALUES (?, ?, ?)",
                (row[0], row[1], today)
            )
    else:
        # Tablo zaten yeni şemada; sadece index'in varlığını garantile
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_budget_limits_category ON budget_limits(category)"
        )


# ─── Expense Functions ─────────────────────────────────────────

def add_expense(amount: float, category: str, description: str = "",
                currency: str = "TRY", date: str = None) -> int:
    """Yeni harcama ekler, ID döndürür."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO expenses (amount, currency, category, description, date) VALUES (?, ?, ?, ?, ?)",
        (amount, currency, category, description, date)
    )
    conn.commit()
    expense_id = cur.lastrowid
    conn.close()
    return expense_id


def get_expenses(month: int = None, year: int = None, category: str = None) -> list[dict]:
    """Filtreye göre harcamaları getirir."""
    conn = get_connection()
    query = "SELECT * FROM expenses WHERE 1=1"
    params = []

    if month and year:
        start = f"{year}-{month:02d}-01"
        if month == 12:
            end = f"{year + 1}-01-01"
        else:
            end = f"{year}-{month + 1:02d}-01"
        query += " AND date >= ? AND date < ?"
        params.extend([start, end])
    elif year:
        query += " AND date >= ? AND date < ?"
        params.extend([f"{year}-01-01", f"{year + 1}-01-01"])

    if category:
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY date DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_monthly_summary(month: int = None, year: int = None) -> dict:
    """Aylık harcama özeti döndürür."""
    now = datetime.now()
    if not month:
        month = now.month
    if not year:
        year = now.year

    expenses = get_expenses(month=month, year=year)
    total = sum(e["amount"] for e in expenses)

    by_category = {}
    for e in expenses:
        cat = e["category"]
        by_category[cat] = by_category.get(cat, 0) + e["amount"]
    by_category = {k: round(v, 2) for k, v in sorted(by_category.items(), key=lambda x: -x[1])}

    # Geçen ay ile karşılaştırma
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    prev_expenses = get_expenses(month=prev_month, year=prev_year)
    prev_total = sum(e["amount"] for e in prev_expenses)
    change_pct = ((total - prev_total) / prev_total * 100) if prev_total > 0 else 0

    top_category = max(by_category, key=by_category.get) if by_category else "Yok"

    return {
        "month": month,
        "year": year,
        "total": round(total, 2),
        "transaction_count": len(expenses),
        "by_category": by_category,
        "top_category": top_category,
        "top_category_amount": by_category.get(top_category, 0),
        "prev_month_total": round(prev_total, 2),
        "change_percent": round(change_pct, 1),
        "expenses": expenses,
    }


def delete_expense(expense_id: int) -> bool:
    """Harcama siler."""
    conn = get_connection()
    cur = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ─── Budget Limit Functions ────────────────────────────────────

def get_limit_for_month(category: str, month: int, year: int) -> float:
    """
    Belirli bir aya ait geçerli bütçe limitini döndürür.
    O aya ait valid_from <= target <= valid_to (veya NULL) koşulunu sağlayan kaydı bulur.
    """
    target_date = f"{year}-{month:02d}-01"
    conn = get_connection()
    row = conn.execute("""
        SELECT monthly_limit FROM budget_limits
        WHERE category = ?
          AND valid_from <= ?
          AND (valid_to IS NULL OR valid_to > ?)
        ORDER BY valid_from DESC
        LIMIT 1
    """, (category, target_date, target_date)).fetchone()
    conn.close()

    if row:
        return float(row["monthly_limit"])

    # DB'de yok → config'den default al
    try:
        from config import CATEGORY_BY_ID
        cat_config = CATEGORY_BY_ID.get(category, {})
        return float(cat_config.get("default_limit", 2000.0))
    except Exception:
        return 2000.0


def get_budget_limit(category: str, default: float = None) -> float:
    """
    Kategorinin bugün için geçerli aylık bütçe limitini getirir.
    Geriye dönük uyumluluk için korundu.
    """
    now = datetime.now()
    return get_limit_for_month(category, now.month, now.year)


def set_budget_limit(category: str, limit: float):
    """
    Aktif limiti kapatır, yeni dönem başlatır.
    Bu ay başından (1'inden) itibaren geçerli olacak şekilde kaydeder.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()

    # Mevcut aktif kaydı kapat
    conn.execute("""
        UPDATE budget_limits SET valid_to = ?
        WHERE category = ? AND valid_to IS NULL
    """, (today, category))

    # Yeni dönem aç (bu ayın başından itibaren geçerli)
    month_start = datetime.now().strftime("%Y-%m-01")
    conn.execute("""
        INSERT INTO budget_limits (category, monthly_limit, valid_from)
        VALUES (?, ?, ?)
    """, (category, limit, month_start))

    conn.commit()
    conn.close()


def get_all_budget_limits() -> list[dict]:
    """Şu an aktif olan tüm bütçe limitlerini döndürür."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT category, monthly_limit, valid_from
        FROM budget_limits
        WHERE valid_to IS NULL
        ORDER BY category
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_budget_limit(category: str) -> bool:
    """Bir kategorinin aktif limitini siler (valid_to = bugün olarak kapatır)."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    cur = conn.execute("""
        UPDATE budget_limits SET valid_to = ?
        WHERE category = ? AND valid_to IS NULL
    """, (today, category))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def get_monthly_history() -> list[dict]:
    """
    Harcama kaydı olan tüm ayların özet listesini döndürür.
    Her ay için o aya ait doğru limiti kullanır.
    """
    conn = get_connection()
    months_raw = conn.execute("""
        SELECT
            CAST(strftime('%Y', date) AS INTEGER) as year,
            CAST(strftime('%m', date) AS INTEGER) as month,
            SUM(amount) as total_spent
        FROM expenses
        GROUP BY year, month
        ORDER BY year DESC, month DESC
    """).fetchall()
    conn.close()

    month_names_tr = [
        "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
        "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"
    ]

    result = []
    for row in months_raw:
        y, m = row["year"], row["month"]
        spent = round(row["total_spent"], 2)

        # O aya ait tüm kategorilerin limitini topla
        conn2 = get_connection()
        categories = conn2.execute(
            "SELECT DISTINCT category FROM expenses WHERE strftime('%Y-%m', date) = ?",
            (f"{y}-{m:02d}",)
        ).fetchall()
        conn2.close()

        total_limit = sum(
            get_limit_for_month(row["category"], m, y)
            for row in categories
        )

        balance = round(total_limit - spent, 2)
        result.append({
            "year": y,
            "month": m,
            "label": f"{month_names_tr[m]} {y}",
            "total_limit": round(total_limit, 2),
            "total_spent": spent,
            "balance": balance,
            "status": "profit" if balance >= 0 else "loss",
        })

    return result


def get_lifetime_balance() -> float:
    """
    Tüm zamanların net kâr/zararını döndürür.
    Σ(limitler) - Σ(harcamalar)
    """
    history = get_monthly_history()
    return round(sum(m["balance"] for m in history), 2)


# ─── Chat History Functions ────────────────────────────────────

def save_chat(user_message: str, ai_response: str, agent: str = "general",
              intent: str = "", decision: str = None, notion_url: str = None) -> int:
    """Sohbet geçmişine bir kayıt ekler."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO chat_history
           (user_message, ai_response, agent, intent, decision, notion_url)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_message, ai_response, agent, intent, decision, notion_url)
    )
    conn.commit()
    chat_id = cur.lastrowid
    conn.close()
    return chat_id

def get_chat_history(limit: int = 50) -> list[dict]:
    """Son N sohbeti zaman sırasına göre döndürür."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM chat_history ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]

def clear_chat_history() -> int:
    """Tüm sohbet geçmişini siler. Silinen kayıt sayısını döndürür."""
    conn = get_connection()
    cur = conn.execute("DELETE FROM chat_history")
    conn.commit()
    count = cur.rowcount
    conn.close()
    return count


# ─── App Settings Functions ────────────────────────────────────

def set_setting(key: str, value: str):
    """Bir uygulama ayarını kaydeder/günceller."""
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
        (key, value)
    )
    conn.commit()
    conn.close()

def get_setting(key: str, default: str = "") -> str:
    """Bir uygulama ayarını okur."""
    conn = get_connection()
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default

def get_all_settings() -> dict:
    """Tüm uygulama ayarlarını döndürür."""
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}
