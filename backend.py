
import os
import json
import hmac
import hashlib
import requests
from datetime import datetime, timezone

from io import BytesIO
from urllib.parse import quote

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from dotenv import load_dotenv

from ai_agent import analyze_feedback
from common import (
    save_message,
    save_review,
    update_review_status,
)

load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

app = FastAPI(
    title="Niloufer AI Review Agent",
    version="0.2.0",
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
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v23.0")

ALLOW_UNVERIFIED = (
    os.getenv("ALLOW_UNVERIFIED_WEBHOOKS", "false").lower()
    == "true"
)

ENABLE_TEST_REVIEW = (
    os.getenv("ENABLE_TEST_REVIEW", "false").lower()
    == "true"
)

ENABLE_AI_TEST = (
    os.getenv("ENABLE_AI_TEST", "false").lower()
    == "true"
)


# ============================================================
# WHATSAPP MESSAGING
# ============================================================

def send_whatsapp_text(to: str, message_text: str):
    """
    Send a text message using the WhatsApp Cloud API.

    If WhatsApp credentials are missing, use dry-run mode.
    """

    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        print(
            f"[DRY RUN] WhatsApp reply to {to}: "
            f"{message_text}"
        )
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
            "body": message_text,
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


# ============================================================
# MANAGER NOTIFICATIONS
# ============================================================

def notify_manager(review: dict, analysis: dict):
    """
    Notify the configured manager webhook about
    negative or mixed customer feedback.
    """

    url = os.getenv("MANAGER_WEBHOOK_URL")

    if not url:
        print(
            f"[MANAGER ALERT] Negative/mixed review "
            f"{review.get('id')}: "
            f"{analysis.get('summary')}"
        )
        return

    payload = {
        "event": "customer_feedback_flagged",
        "review_id": review.get("id"),
        "sentiment": analysis.get("sentiment"),
        "category": analysis.get("category"),
        "summary": analysis.get("summary"),
        "branch_id": review.get(
            "branch_id",
            "niloufer-main",
        ),
        "complaint_status": review.get(
            "complaint_status",
            "pending",
        ),
    }

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()

    except Exception as exc:
        print(f"Manager notification failed: {exc}")


# ============================================================
# WHATSAPP SIGNATURE VERIFICATION
# ============================================================

def verify_signature(
    raw_body: bytes,
    signature: str | None,
) -> bool:
    """
    Validate Meta's webhook signature.

    Production recommendation:
    Configure WHATSAPP_APP_SECRET in Render.
    """

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


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/")
def health():
    return {
        "status": "ok",
        "service": "Niloufer AI Review Agent",
        "whatsapp_configured": bool(
            ACCESS_TOKEN and PHONE_NUMBER_ID
        ),
        "database_configured": bool(
            os.getenv("SUPABASE_URL")
            and os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        ),
    }


# ============================================================
# LIST REVIEWS
# ============================================================

@app.get("/api/reviews")
def list_reviews():
    from common import get_reviews

    try:
        reviews = get_reviews()

        return {
            "reviews": reviews,
            "total_reviews": len(reviews),
        }

    except Exception as exc:
        print(f"Failed to retrieve reviews: {exc}")

        raise HTTPException(
            status_code=500,
            detail=(
                "Could not retrieve reviews. "
                "Check backend logs."
            ),
        )


# ============================================================
# AI CUSTOMER FEEDBACK REPORT
# ============================================================

@app.post("/api/ai-report")
def generate_ai_report():
    """Calculate exact sentiment statistics and ask the AI for evidence-based recommendations."""
    from collections import Counter, defaultdict
    from common import get_reviews

    try:
        reviews = get_reviews()
    except Exception as exc:
        print(f"AI report: could not load reviews: {exc}")
        raise HTTPException(status_code=500, detail="Could not load reviews from the database.")

    if not reviews:
        raise HTTPException(status_code=400, detail="No reviews are available yet. Collect customer feedback before generating a report.")

    allowed = {"positive", "negative", "mixed", "neutral"}
    counts = Counter(str(r.get("sentiment", "neutral")).lower() for r in reviews)
    for label in allowed:
        counts.setdefault(label, 0)
    total = len(reviews)
    percentages = {label: round(counts[label] * 100 / total, 1) for label in ("positive", "negative", "mixed", "neutral")}

    category_counts = defaultdict(lambda: {"total": 0, "negative": 0, "mixed": 0})
    for review in reviews:
        category = str(review.get("category") or "other").lower()
        category_counts[category]["total"] += 1
        sentiment = str(review.get("sentiment") or "neutral").lower()
        if sentiment in ("negative", "mixed"):
            category_counts[category][sentiment] += 1
    category_breakdown = [
        {"category": category, **values}
        for category, values in sorted(category_counts.items(), key=lambda item: (-(item[1]["negative"] + item[1]["mixed"]), -item[1]["total"]))
    ]

    review_evidence = []
    for r in reviews[:250]:
        review_evidence.append({
            "sentiment": r.get("sentiment"),
            "category": r.get("category"),
            "rating": r.get("rating"),
            "summary": r.get("ai_summary"),
            "review": str(r.get("review_text") or "")[:500],
        })

    executive_summary = ""
    recommendations = []
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            prompt = {
                "task": "Analyze restaurant customer feedback and return valid JSON only.",
                "rules": [
                    "Use only evidence in the provided reviews; do not invent customer claims.",
                    "Prioritize recurring actionable issues; if data is sparse, say so.",
                    "Keep recommendations practical and specific for a cafe.",
                    "Do not recalculate or alter the supplied sentiment percentages.",
                    "Return keys executive_summary (string) and recommendations (array of objects with priority High/Medium/Low, title, evidence, action). Return 3-6 recommendations if evidence supports them, otherwise fewer."
                ],
                "calculated_statistics": {"total_reviews": total, "sentiment_counts": dict(counts), "sentiment_percentages": percentages, "category_breakdown": category_breakdown},
                "reviews": review_evidence,
            }
            completion = client.chat.completions.create(
                model=model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "You are a careful customer-experience analyst for Niloufer Cafe. Return valid JSON only."},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
            )
            generated = json.loads(completion.choices[0].message.content or "{}")
            executive_summary = str(generated.get("executive_summary") or "The available feedback has been summarized. Review category breakdowns to identify improvement opportunities.")
            raw_recommendations = generated.get("recommendations", [])
            if isinstance(raw_recommendations, list):
                for item in raw_recommendations[:8]:
                    if isinstance(item, dict) and item.get("title"):
                        priority = str(item.get("priority", "Medium")).title()
                        if priority not in ("High", "Medium", "Low"):
                            priority = "Medium"
                        recommendations.append({"priority": priority, "title": str(item["title"]), "evidence": str(item.get("evidence", "Based on available customer feedback.")), "action": str(item.get("action", "Review this issue and monitor future feedback."))})
        except Exception as exc:
            print(f"AI report generation failed: {exc}")
            raise HTTPException(status_code=502, detail="AI report generation failed. Check OPENAI_API_KEY, OPENAI_MODEL, and Render logs.")
    else:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured on the backend.")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_reviews": total,
        "sentiment_counts": {label: counts[label] for label in ("positive", "negative", "mixed", "neutral")},
        "sentiment_percentages": percentages,
        "category_breakdown": category_breakdown,
        "executive_summary": executive_summary,
        "recommendations": recommendations,
    }


# ============================================================
# TEMPORARY DATABASE TEST
# ENABLE ONLY WHILE TESTING
# ============================================================

@app.post("/api/test-review")
def test_review_storage():
    if not ENABLE_TEST_REVIEW:
        raise HTTPException(
            status_code=404,
            detail="Not found",
        )

    from common import get_reviews

    analysis = {
        "sentiment": "positive",
        "category": "food_quality",
        "rating": 5,
        "summary": "Temporary database connection test.",
    }

    try:
        review = save_review(
            whatsapp_id="test-customer",
            review_text=(
                "Temporary test review. "
                "Delete after verification."
            ),
            analysis=analysis,
            message_id=None,
            source="portal_demo",
        )

        return {
            "success": True,
            "review": review,
            "total_reviews": len(get_reviews()),
        }

    except Exception as exc:
        print(f"Test review failed: {exc}")

        raise HTTPException(
            status_code=500,
            detail=(
                "Review storage test failed. "
                "Check Render logs."
            ),
        )


# ============================================================
# TEMPORARY OPENAI TEST
# ENABLE ONLY WHILE TESTING
# ============================================================

@app.post("/api/test-ai")
def test_ai():
    """
    Test the existing AI analysis function without
    inserting a review into the database.

    Note:
    If ai_agent.py catches OpenAI errors and returns
    fallback output, inspect Render logs as well.
    """

    if not ENABLE_AI_TEST:
        raise HTTPException(
            status_code=404,
            detail="Not found",
        )

    test_message = (
        "The Irani chai was delicious, "
        "but the service was slow."
    )

    try:
        analysis = analyze_feedback(test_message)

        if not isinstance(analysis, dict):
            raise ValueError(
                "analyze_feedback did not return a dictionary."
            )

        required_fields = [
            "sentiment",
            "category",
            "rating",
            "summary",
            "reply",
        ]

        missing_fields = [
            field
            for field in required_fields
            if field not in analysis
        ]

        return {
            "success": True,
            "test_message": test_message,
            "analysis": analysis,
            "missing_fields": missing_fields,
            "note": (
                "Check the analysis and Render logs to "
                "confirm whether OpenAI generated the result."
            ),
        }

    except Exception as exc:
        print(f"AI test failed: {exc}")

        raise HTTPException(
            status_code=500,
            detail=(
                "AI test failed. "
                "Check Render logs for the actual error."
            ),
        )


# ============================================================
# UPDATE REVIEW STATUS
# ============================================================

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
        result = update_review_status(
            review_id,
            status,
        )

        return {
            "ok": True,
            "result": result,
        }

    except Exception as exc:
        print(f"Could not update review status: {exc}")

        raise HTTPException(
            status_code=500,
            detail=(
                "Could not update review status."
            ),
        )


# ============================================================
# WHATSAPP WEBHOOK VERIFICATION
# ============================================================

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


# ============================================================
# RECEIVE WHATSAPP MESSAGES
# ============================================================

@app.post("/webhook/whatsapp")
async def receive_webhook(request: Request):
    raw = await request.body()

    signature = request.headers.get(
        "X-Hub-Signature-256"
    )

    if not verify_signature(raw, signature):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature",
        )

    try:
        payload = json.loads(
            raw.decode("utf-8")
        )

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

                if (
                    not wa_id
                    or not message_text
                    or not message_id
                ):
                    continue

                # Save the incoming message.
                try:
                    fresh = save_message(
                        wa_id,
                        "incoming",
                        message_text,
                        message_id,
                    )

                except Exception as exc:
                    print(
                        "Could not save incoming message: "
                        f"{exc}"
                    )
                    continue

                # Avoid processing duplicate webhook deliveries.
                if not fresh:
                    continue

                # Handle opt-out requests.
                if message_text.lower() in {
                    "stop",
                    "unsubscribe",
                    "opt out",
                }:
                    opt_out_reply = (
                        "You've been opted out of feedback "
                        "messages. If you need help, please "
                        "contact Niloufer Café directly."
                    )

                    try:
                        send_whatsapp_text(
                            wa_id,
                            opt_out_reply,
                        )

                        save_message(
                            wa_id,
                            "outgoing",
                            opt_out_reply,
                            None,
                            "sent",
                        )

                    except Exception as exc:
                        print(
                            "Could not send opt-out reply: "
                            f"{exc}"
                        )

                    continue

                # Analyze feedback with the AI agent.
                try:
                    analysis = analyze_feedback(
                        message_text
                    )

                except Exception as exc:
                    print(
                        f"Feedback analysis failed: {exc}"
                    )
                    continue

                # Save the analyzed review.
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

                # Send the AI-generated response.
                try:
                    reply = analysis.get("reply")

                    if not reply:
                        raise ValueError(
                            "AI analysis did not contain a reply."
                        )

                    send_whatsapp_text(
                        wa_id,
                        reply,
                    )

                    save_message(
                        wa_id,
                        "outgoing",
                        reply,
                        None,
                        "sent",
                    )

                except Exception as exc:
                    print(
                        "Could not send WhatsApp reply: "
                        f"{exc}"
                    )

                # Notify the manager about negative feedback.
                if analysis.get("sentiment") in {
                    "negative",
                    "mixed",
                }:
                    notify_manager(
                        review if isinstance(
                            review, dict
                        ) else {},
                        analysis,
                    )

    return {
        "status": "received",
    }


# ============================================================
# WHATSAPP QR CODE
# ============================================================

@app.get("/qr")
def get_qr():
    number = (
        os.getenv("WHATSAPP_PUBLIC_NUMBER", "")
        .strip()
        .replace("+", "")
        .replace(" ", "")
        .replace("-", "")
    )

    if not number:
        raise HTTPException(
            status_code=503,
            detail=(
                "Set WHATSAPP_PUBLIC_NUMBER in Render "
                "using international digits only."
            ),
        )

    import qrcode

    link = (
        f"https://wa.me/{number}"
        "?text="
        + quote(
            "Hi Niloufer Cafe, I'd like to share feedback."
        )
    )

    img = qrcode.make(link)

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store",
        },
    )
