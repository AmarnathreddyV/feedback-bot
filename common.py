import os
import sqlite3
import json
from datetime import datetime, timezone
from typing import Any
from dotenv import load_dotenv

load_dotenv()
SQLITE_PATH = os.getenv("SQLITE_PATH", "./niloufer_reviews.db")

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def _sqlite():
    conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS customers (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      whatsapp_id TEXT UNIQUE NOT NULL,
      consent_status TEXT NOT NULL DEFAULT 'unknown',
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS reviews (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      customer_id INTEGER,
      whatsapp_id TEXT,
      branch_id TEXT NOT NULL DEFAULT 'niloufer-main',
      review_text TEXT NOT NULL,
      sentiment TEXT NOT NULL,
      category TEXT NOT NULL,
      rating INTEGER,
      ai_summary TEXT,
      complaint_status TEXT NOT NULL DEFAULT 'not_applicable',
      source TEXT NOT NULL DEFAULT 'whatsapp_qr',
      whatsapp_message_id TEXT UNIQUE,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      customer_id INTEGER,
      whatsapp_id TEXT,
      direction TEXT NOT NULL,
      message_text TEXT NOT NULL,
      whatsapp_message_id TEXT UNIQUE,
      status TEXT NOT NULL DEFAULT 'received',
      created_at TEXT NOT NULL
    );
    """)
    conn.commit()
    return conn

def _supabase_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    from supabase import create_client
    return create_client(url, key)

def save_message(whatsapp_id: str, direction: str, text: str, message_id: str | None = None, status: str = "received"):
    now = utc_now()
    try:
        sb = _supabase_client()
        if sb:
            payload = {"whatsapp_id": whatsapp_id, "direction": direction, "message_text": text,
                       "whatsapp_message_id": message_id, "status": status, "created_at": now}
            if message_id:
                existing = sb.table("messages").select("id").eq("whatsapp_message_id", message_id).limit(1).execute().data
                if existing:
                    return False
            sb.table("messages").insert(payload).execute()
            return True
        with _sqlite() as conn:
            if message_id and conn.execute("SELECT 1 FROM messages WHERE whatsapp_message_id=?", (message_id,)).fetchone():
                return False
            conn.execute("""INSERT INTO messages (whatsapp_id,direction,message_text,whatsapp_message_id,status,created_at)
                            VALUES (?,?,?,?,?,?)""", (whatsapp_id,direction,text,message_id,status,now))
            conn.commit()
        return True
    except Exception as exc:
        print(f"save_message error: {exc}")
        return False

def save_review(whatsapp_id: str, review_text: str, analysis: dict[str, Any], message_id: str | None = None,
                source: str = "whatsapp_qr", branch_id: str = "niloufer-main"):
    now = utc_now()
    complaint_status = "pending" if analysis["sentiment"] in ("negative", "mixed") else "not_applicable"
    payload = {
        "whatsapp_id": whatsapp_id, "branch_id": branch_id, "review_text": review_text,
        "sentiment": analysis["sentiment"], "category": analysis["category"],
        "rating": analysis.get("rating"), "ai_summary": analysis["summary"],
        "complaint_status": complaint_status, "source": source,
        "whatsapp_message_id": message_id, "created_at": now, "updated_at": now
    }
    sb = _supabase_client()
    if sb:
        try:
            result = sb.table("reviews").insert(payload).execute()
            return result.data[0] if result.data else payload
        except Exception as exc:
            print(f"Supabase review insert error: {exc}")
            # Avoid silently duplicating data in SQLite when Supabase is configured.
            raise
    with _sqlite() as conn:
        cur = conn.execute("""INSERT INTO reviews
          (whatsapp_id,branch_id,review_text,sentiment,category,rating,ai_summary,complaint_status,source,
           whatsapp_message_id,created_at,updated_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
          (whatsapp_id,branch_id,review_text,analysis["sentiment"],analysis["category"],analysis.get("rating"),
           analysis["summary"],complaint_status,source,message_id,now,now))
        conn.commit()
        return dict(id=cur.lastrowid, **payload)

def get_reviews():
    sb = _supabase_client()
    if sb:
        return sb.table("reviews").select("*").order("created_at", desc=True).limit(5000).execute().data or []
    with _sqlite() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM reviews ORDER BY created_at DESC LIMIT 5000").fetchall()]

def update_review_status(review_id, status):
    if status not in ("pending", "in_progress", "resolved", "not_applicable"):
        raise ValueError("Invalid complaint status")
    sb = _supabase_client()
    if sb:
        return sb.table("reviews").update({"complaint_status": status, "updated_at": utc_now()}).eq("id", review_id).execute().data
    with _sqlite() as conn:
        conn.execute("UPDATE reviews SET complaint_status=?, updated_at=? WHERE id=?", (status, utc_now(), review_id))
        conn.commit()

def create_demo_reviews():
    existing = get_reviews()
    if existing:
        return 0
    samples = [
        ("The Irani chai was amazing and the service was excellent.", "positive", "food_quality", "Excellent chai and service.", "whatsapp_qr"),
        ("My chai was cold and we waited 25 minutes.", "negative", "service", "Cold chai and long waiting time.", "whatsapp_invitation"),
        ("Great chai, but the tables were dirty.", "mixed", "cleanliness", "Positive chai feedback with a table cleanliness complaint.", "whatsapp_qr"),
        ("Prices are a little high for the portion size.", "negative", "pricing", "Concern about pricing and portion size.", "whatsapp_qr"),
        ("Nice ambience, will visit again.", "positive", "ambience", "Positive ambience feedback.", "whatsapp_invitation"),
    ]
    for i, (txt, sentiment, category, summary, source) in enumerate(samples, start=1):
        save_review(f"demo-customer-{i}", txt, {"sentiment":sentiment,"category":category,"rating":None,"summary":summary},
                    message_id=f"demo-{i}", source="portal_demo")
    return len(samples)

def mark_customer_consent(whatsapp_id: str, status: str):
    if status not in ("unknown", "opted_in", "opted_out"):
        raise ValueError("Invalid consent status")
    now = utc_now()
    sb = _supabase_client()
    if sb:
        existing = sb.table("customers").select("id").eq("whatsapp_id", whatsapp_id).limit(1).execute().data
        payload = {"whatsapp_id": whatsapp_id, "consent_status": status, "updated_at": now}
        if existing:
            return sb.table("customers").update(payload).eq("whatsapp_id", whatsapp_id).execute().data
        return sb.table("customers").insert(payload | {"created_at": now}).execute().data
    with _sqlite() as conn:
        conn.execute("""INSERT INTO customers (whatsapp_id, consent_status, created_at)
          VALUES (?,?,?) ON CONFLICT(whatsapp_id) DO UPDATE SET consent_status=excluded.consent_status""",
          (whatsapp_id,status,now))
        conn.commit()
