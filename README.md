# Niloufer AI Review Agent

A starter application for a café feedback workflow with:
- WhatsApp Business Cloud API webhook (Meta)
- AI-assisted sentiment/category analysis using OpenAI API (optional)
- Supabase PostgreSQL persistence (optional; SQLite fallback for local development)
- Streamlit management portal
- QR-code entry point for customers to initiate a WhatsApp chat
- Complaint notifications by email webhook URL (optional)

## Architecture

`WhatsApp -> FastAPI webhook -> analysis -> database -> WhatsApp reply -> Streamlit portal`

The same backend handles both customer-initiated QR conversations and opt-in feedback invitations. Sending outbound feedback invitations must be implemented only for opted-in customers and with an approved WhatsApp template when required by Meta's rules.

## Requirements
- Python 3.11+
- Meta developer app with WhatsApp Cloud API configured for live messaging (or Meta test number for development)
- Supabase project (optional locally; SQLite is used when Supabase env vars are absent)
- OpenAI API key (optional; deterministic fallback classification is used without it)

## Setup on Windows

```powershell
cd niloufer_ai_review_agent
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`. Never commit `.env` or publish access tokens.

Run the backend in terminal 1:
```powershell
uvicorn backend:app --reload --host 0.0.0.0 --port 8000
```

Run the dashboard in terminal 2:
```powershell
streamlit run dashboard.py
```

Local webhook testing requires a public HTTPS URL (for example, a temporary tunnel) configured in Meta's webhook settings. Do not expose the local dashboard publicly without authentication.

## Configure Supabase
1. Open the Supabase project SQL Editor.
2. Run `sql/schema.sql`.
3. Copy the project URL and a server-side secret/service-role key into `.env`.
4. Keep that key only on the backend. Do not put it in browser/client code or commit it to Git.

Supabase Python client documentation: https://supabase.com/docs/reference/python/start

## Configure WhatsApp Cloud API
Set these values in `.env`:
- `WHATSAPP_ACCESS_TOKEN`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_VERIFY_TOKEN` (a secret string you choose for webhook verification)
- `WHATSAPP_APP_SECRET` (recommended, to validate webhook signatures)
- `WHATSAPP_API_VERSION` (use the Graph API version currently shown in your Meta app documentation)

Configure a webhook callback URL pointing to `/webhook/whatsapp`, subscribe to the `messages` field, and use the same verify token. Meta's webhook must be reachable over HTTPS.

Meta WhatsApp Cloud API documentation: https://developers.facebook.com/docs/whatsapp/cloud-api/

## AI setup
Set `OPENAI_API_KEY` and optionally `OPENAI_MODEL` in `.env`. If no key is provided, a rule-based classifier will be used. Keep API keys private.

## Management notifications
Set `MANAGER_WEBHOOK_URL` to an internal automation/webhook endpoint if you want a manager alert for negative/mixed feedback. The request includes review ID, sentiment, category, summary, and branch ID—not the customer's full message unless you change the code.

## QR code
Run the backend, then open:
`http://localhost:8000/qr`
The QR points to `WHATSAPP_PUBLIC_NUMBER` (international format, digits only). For production, set this to the café's actual WhatsApp Business number. A QR can be generated only after the number is configured. The customer must send the prefilled message to initiate the chat.

## Important production checklist
- Use customer opt-in for proactive messages.
- Use approved templates when required outside the customer-service window.
- Add dashboard authentication and role-based access before publishing.
- Verify Meta webhook signatures in production (`WHATSAPP_APP_SECRET`).
- Configure HTTPS and secret management.
- Add privacy notice, retention/deletion policy, and consent handling.
- Test duplicate webhook delivery and monitor API errors.
- Do not treat AI sentiment labels as infallible; allow managers to correct them.
