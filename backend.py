import os
import json
import hmac
import hashlib
import requests

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from ai_agent import analyze_feedback
from common import save_message, save_review, update_review_status


# --------------------------------------------------
# Configuration
# --------------------------------------------------

load_dotenv()

app = FastAPI(
    title="Niloufer AI Review Agent",
    version="0.1.0",
)

FRONTEND_ORIGIN = os.getenv(
    "FRONTEND_ORIGIN",
    "https://feedback-bot-sepia.vercel.app",
)

allowed_origins = [
    origin.strip().rstrip("/")
    for origin in FRONTEND_ORIGIN.split(",")
    if origin.strip()
]

production_origin = "https://feedback-bot-sepia.vercel.app"

if production_origin not in allowed_origins:
    allowed_origins.append(production_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# --------------------------------------------------
# WhatsApp Configuration
# --------------------------------------------------

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v23.0")

ALLOW_UNVERIFIED = (
    os.getenv("ALLOW_UNVERIFIED_WEBHOOKS", "false").lower()
    == "true"
)


# --------------------------------------------------
# WhatsApp Messaging
# --------------------------------------------------

def send_whatsapp_text(to: str, text: str):
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        print(f"[DRY RUN] WhatsApp reply to {to}: {text}")
        return {"dry_run": True}

    url = (
        f"https://graph.facebook.com/"
        f"{API_VERSION}/{PHONE_NUMBER_ID}/messages"
    )

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text,
        },
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=20,
    )

    if response.status_code >= 400:
        print(
            f"WhatsApp send failed: "
            f"{response.status_code} {response.text}"
        )
        response.raise_for_status()

    return response.json()


# --------------------------------------------------
# Manager Notifications
# --------------------------------------------------

def notify_manager(review: dict, analysis: dict):
    url = os.getenv("MANAGER_WEBHOOK_URL")

    if not url:
        print(
            f"[MANAGER ALERT] Negative/mixed review "
            f"{review.get('id')}: {analysis.get('summary')}"
        )
        return

    payload = {
        "event": "customer_feedback_flagged",
        "review_id": review.get("id"),
        "sentiment": analysis.get("sentiment"),
        "category": analysis.get("category"),
        "summary": analysis.get("summary"),
        "branch_id": review.get("branch_id", "niloufer-main"),
        "complaint_status": review.get(
            "complaint_status",
            "pending",
        ),
    }

    try:
        requests.post(
            url,
            json=payload,
            timeout=10,
        ).raise_for_status()

    except Exception as exc:
        print(f"Manager notification failed: {exc}")


# --------------------------------------------------
# WhatsApp Webhook Signature Verification
# --------------------------------------------------

def verify_signature(
    raw_body: bytes,
    signature: str | None,
) -> bool:
    if not APP_SECRET:
        return ALLOW_UNVERIFIED

    if not signature or not signature.startswith("sha256="):
        return False

    expected = hmac.new(
        APP_SECRET.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    received = signature.split("=", 1)[1]

    return hmac.compare_digest(expected, received)


# --------------------------------------------------
# Health Check
# --------------------------------------------------

@app.get("/")
def health():
    return {
        "status": "ok",
        "service": "Niloufer AI Review Agent",
        "whatsapp_configured": bool(
            ACCESS_TOKEN and PHONE_NUMBER_ID
        ),
    }


# --------------------------------------------------
# List Reviews
# --------------------------------------------------

@app.get("/api/reviews")
def list_reviews():
    from common import get_reviews

    try:
        return {"reviews": get_reviews()}

    except Exception as exc:
        print(f"Failed to retrieve reviews: {exc}")

        raise HTTPException(
            status_code=500,
            detail="Could not retrieve reviews. Check backend logs.",
        )


# --------------------------------------------------
# Update Review Status
# --------------------------------------------------

@app.patch("/api/reviews/{review_id}/status")
def patch_review_status(
    review_id: str,
    payload: dict,
):
    status = payload.get("status")

    allowed_statuses = {
        "pending",
        "in_progress",
        "resolved",
        "not_applicable",
    }

    if status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail="Invalid complaint status",
        )

    try:
        result = update_review_status(review_id, status)

        return {
            "ok": True,
            "result": result,
        }

    except Exception as exc:
        print(f"Could not update review status: {exc}")

        raise HTTPException(
            status_code=500,
            detail="Could not update review status.",
        )


# --------------------------------------------------
# WhatsApp Webhook Verification
# --------------------------------------------------

@app.get("/webhook/whatsapp")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if (
        mode == "subscribe"
        and VERIFY_TOKEN
        and token == VERIFY_TOKEN
    ):
        return PlainTextResponse(challenge or "")

    raise HTTPException(
        status_code=403,
        detail="Webhook verification failed",
    )


# --------------------------------------------------
# Receive WhatsApp Messages
# --------------------------------------------------

@app.post("/webhook/whatsapp")
async def receive_webhook(request: Request):
    raw = await request.body()

    signature = request.headers.get("X-Hub-Signature-256")

    if not verify_signature(raw, signature):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature",
        )

    try:
        payload = json.loads(raw.decode("utf-8"))

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON",
        )

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            for msg in value.get("messages", []) or []:
                if msg.get("type") != "text":
                    continue

                wa_id = msg.get("from")
                message_id = msg.get("id")

                message_text = (
                    msg.get("text", {})
                    .get("body", "")
                    .strip()
                )

                if not wa_id or not message_text or not message_id:
                    continue

                try:
                    fresh = save_message(
                        wa_id,
                        "incoming",
                        message_text,
                        message_id,
                    )

                except Exception as exc:
                    print(f"Could not save incoming message: {exc}")
                    continue

                if not fresh:
                    continue

                if message_text.lower() in {
                    "stop",
                    "unsubscribe",
                    "opt out",
                }:
                    opt_out_reply = (
                        "You've been opted out of feedback messages. "
                        "If you need help, please contact Niloufer Café directly."
                    )

                    send_whatsapp_text(wa_id, opt_out_reply)

                    save_message(
                        wa_id,
                        "outgoing",
                        opt_out_reply,
                        None,
                        "sent",
                    )

                    continue

                try:
                    analysis = analyze_feedback(message_text)

                except Exception as exc:
                    print(f"Feedback analysis failed: {exc}")
                    continue

                try:
                    review = save_review(
                        wa_id,
                        message_text,
                        analysis,
                        message_id=message_id,
                        source="whatsapp_qr",
                    )

                except Exception as exc:
                    print(f"Could not save review: {exc}")
                    continue

                try:
                    reply = analysis["reply"]

                    send_whatsapp_text(wa_id, reply)

                    save_message(
                        wa_id,
                        "outgoing",
                        reply,
                        None,
                        "sent",
                    )

                except Exception as exc:
                    print(f"Could not send WhatsApp reply: {exc}")

                if analysis.get("sentiment") in {
                    "negative",
                    "mixed",
                }:
                    notify_manager(
                        review if isinstance(review, dict) else {},
                        analysis,
                    )

    return {"status": "received"}


# --------------------------------------------------
# Generate WhatsApp QR Code
# --------------------------------------------------

@app.get("/qr")
def get_qr():
    number = (
        os.getenv("WHATSAPP_PUBLIC_NUMBER", "")
        .strip()
        .replace("+", "")
        .replace(" ", "")
    )

    if not number:
        return {
            "error": (
                "Set WHATSAPP_PUBLIC_NUMBER in the environment "
                "using international digits only."
            )
        }

    import qrcode

    from io import BytesIO
    from fastapi.responses import StreamingResponse

    link = (
        f"https://wa.me/{number}"
        "?text=Hi%20Niloufer%20Cafe%2C%20"
        "I%27d%20like%20to%20share%20feedback."
    )

    img = qrcode.make(link)

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="image/png",
    )
