import os
import json
import hmac
import hashlib
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response
from dotenv import load_dotenv
from ai_agent import analyze_feedback
from common import save_message, save_review, update_review_status

load_dotenv()
app = FastAPI(title="Niloufer AI Review Agent", version="0.1.0")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in FRONTEND_ORIGIN.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v23.0")
ALLOW_UNVERIFIED = os.getenv("ALLOW_UNVERIFIED_WEBHOOKS", "false").lower() == "true"

def send_whatsapp_text(to: str, text: str):
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        print(f"[DRY RUN] WhatsApp reply to {to}: {text}")
        return {"dry_run": True}
    url = f"https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product":"whatsapp", "recipient_type":"individual", "to":to,
               "type":"text", "text":{"preview_url":False,"body":text}}
    response = requests.post(url, headers=headers, json=payload, timeout=20)
    if response.status_code >= 400:
        print(f"WhatsApp send failed: {response.status_code} {response.text}")
        response.raise_for_status()
    return response.json()

def notify_manager(review: dict, analysis: dict):
    url = os.getenv("MANAGER_WEBHOOK_URL")
    if not url:
        print(f"[MANAGER ALERT] Negative/mixed review {review.get('id')}: {analysis.get('summary')}")
        return
    payload = {
        "event": "customer_feedback_flagged",
        "review_id": review.get("id"),
        "sentiment": analysis.get("sentiment"),
        "category": analysis.get("category"),
        "summary": analysis.get("summary"),
        "branch_id": review.get("branch_id", "niloufer-main"),
        "complaint_status": review.get("complaint_status", "pending"),
    }
    try:
        requests.post(url, json=payload, timeout=10).raise_for_status()
    except Exception as exc:
        print(f"Manager notification failed: {exc}")

def verify_signature(raw_body: bytes, signature: str | None):
    if not APP_SECRET:
        return ALLOW_UNVERIFIED
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.split("=", 1)[1])

@app.get("/api/reviews")
def list_reviews():
    from common import get_reviews
    return {"reviews": get_reviews()}

@app.patch("/api/reviews/{review_id}/status")
def patch_review_status(review_id: str, payload: dict):
    status = payload.get("status")
    if status not in ("pending", "in_progress", "resolved", "not_applicable"):
        raise HTTPException(status_code=400, detail="Invalid complaint status")
    try:
        update_result = __import__("common").update_review_status(review_id, status)
        return {"ok": True, "result": update_result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not update review status: {exc}")

@app.get("/")
def health():
    return {"status":"ok", "service":"Niloufer AI Review Agent", "whatsapp_configured":bool(ACCESS_TOKEN and PHONE_NUMBER_ID)}

@app.get("/webhook/whatsapp")
def verify_webhook(request: Request):
    # FastAPI's Request query params are available here too.
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and VERIFY_TOKEN and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge or "")
    raise HTTPException(status_code=403, detail="Webhook verification failed")

@app.post("/webhook/whatsapp")
async def receive_webhook(request: Request):
    raw = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(raw, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []) or []:
                if msg.get("type") != "text":
                    continue
                wa_id = msg.get("from")
                message_id = msg.get("id")
                text = msg.get("text", {}).get("body", "").strip()
                if not wa_id or not text or not message_id:
                    continue
                # Save incoming message first. Duplicate webhook deliveries are ignored.
                fresh = save_message(wa_id, "incoming", text, message_id)
                if not fresh:
                    continue
                if text.lower().strip() in {"stop", "unsubscribe", "opt out"}:
                    send_whatsapp_text(wa_id, "You've been opted out of feedback messages. If you need help, please contact Niloufer Café directly.")
                    save_message(wa_id, "outgoing", "You've been opted out of feedback messages.", None, "sent")
                    continue

                analysis = analyze_feedback(text)
                review = None
                # Save only messages that appear to contain feedback; neutral messages are retained too for context.
                try:
                    review = save_review(wa_id, text, analysis, message_id=message_id, source="whatsapp_qr")
                except Exception as exc:
                    print(f"Could not save review; no reply sent: {exc}")
                    continue

                send_whatsapp_text(wa_id, analysis["reply"])
                save_message(wa_id, "outgoing", analysis["reply"], None, "sent")
                if analysis["sentiment"] in ("negative", "mixed"):
                    notify_manager(review if isinstance(review, dict) else {}, analysis)

    return {"status":"received"}

@app.get("/qr")
def get_qr():
    number = os.getenv("WHATSAPP_PUBLIC_NUMBER", "").strip().replace("+", "").replace(" ", "")
    if not number:
        return {"error":"Set WHATSAPP_PUBLIC_NUMBER in .env using international digits only."}
    import qrcode
    from io import BytesIO
    from fastapi.responses import StreamingResponse
    link = f"https://wa.me/{number}?text=Hi%20Niloufer%20Cafe%2C%20I%27d%20like%20to%20share%20feedback."
    img = qrcode.make(link)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")
