# Niloufer Review Portal — Next.js

This folder is the web portal frontend. It replaces Streamlit.

## Run locally
```bash
npm install
cp .env.example .env.local
npm run dev
```
Open http://localhost:3000.

Set `NEXT_PUBLIC_API_URL` to the public URL of the FastAPI backend. For local development, use `http://localhost:8000`.

The dashboard requests `GET /api/reviews` and updates complaint status through `PATCH /api/reviews/{id}/status`.

## Deploy
Deploy this `frontend` directory as a Next.js project (for example on Vercel). Set `NEXT_PUBLIC_API_URL` to the deployed FastAPI backend URL.

The API URL is public by design. Never place Supabase service-role keys, OpenAI API keys, or WhatsApp tokens in `NEXT_PUBLIC_*` variables.

Before production, protect this portal with authentication and enforce tenant isolation on the backend/database.
