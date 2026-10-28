# Niloufer AI Review Agent

This project uses a **Next.js + React portal** (not Streamlit), a Python FastAPI backend, and Supabase PostgreSQL.

## Folders
- `frontend/` — Next.js portal for dashboard, reviews, complaints, reports export.
- `backend.py`, `ai_agent.py`, `common.py` — FastAPI, AI classification, database operations.
- `sql/schema.sql` — Supabase database schema.

## Run locally
Backend:
```bash
python -m venv .venv
# Windows PowerShell: .\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
uvicorn backend:app --reload --port 8000
```
Frontend in another terminal:
```bash
cd frontend
npm install
# copy .env.example to .env.local; default API is http://localhost:8000
npm run dev
```
Open http://localhost:3000.

## Deployment
1. Deploy backend root on Render with start command `uvicorn backend:app --host 0.0.0.0 --port $PORT`.
2. Configure backend environment variables using `.env.example` as a guide.
3. Set `FRONTEND_ORIGIN` to the deployed frontend URL in backend environment variables.
4. Deploy `frontend/` to Vercel as a Next.js project and set `NEXT_PUBLIC_API_URL` to the deployed backend URL.
5. Run `sql/schema.sql` in Supabase SQL Editor if you haven't already.

The backend uses local SQLite if Supabase variables are absent. Configure Supabase for persistent cloud data.
Do not commit secrets. Do not expose the Supabase service-role key or OpenAI/WhatsApp tokens in frontend variables. Add authentication and tenant-level data isolation before real customer data is used.

WhatsApp documentation: https://developers.facebook.com/docs/whatsapp/cloud-api/
