create extension if not exists pgcrypto;

create table if not exists public.customers (
    id uuid primary key default gen_random_uuid(),
    whatsapp_id text not null unique,
    consent_status text not null default 'unknown'
        check (consent_status in ('unknown','opted_in','opted_out')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.reviews (
    id uuid primary key default gen_random_uuid(),
    customer_id uuid references public.customers(id) on delete set null,
    whatsapp_id text,
    branch_id text not null default 'niloufer-main',
    review_text text not null,
    sentiment text not null check (sentiment in ('positive','negative','mixed','neutral')),
    category text not null default 'general',
    rating integer check (rating between 1 and 5),
    ai_summary text not null default '',
    complaint_status text not null default 'not_applicable'
        check (complaint_status in ('not_applicable','pending','in_progress','resolved')),
    source text not null default 'whatsapp_qr'
        check (source in ('whatsapp_qr','whatsapp_invitation','portal_demo')),
    whatsapp_message_id text unique,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.messages (
    id uuid primary key default gen_random_uuid(),
    customer_id uuid references public.customers(id) on delete set null,
    whatsapp_id text,
    direction text not null check (direction in ('incoming','outgoing')),
    message_text text not null,
    whatsapp_message_id text unique,
    status text not null default 'received',
    created_at timestamptz not null default now()
);

create index if not exists reviews_created_at_idx on public.reviews(created_at desc);
create index if not exists reviews_sentiment_idx on public.reviews(sentiment);
create index if not exists reviews_branch_idx on public.reviews(branch_id);
create index if not exists messages_whatsapp_id_idx on public.messages(whatsapp_id);

alter table public.customers enable row level security;
alter table public.reviews enable row level security;
alter table public.messages enable row level security;

-- Keep tables private to the backend service role. Do not add public/anon read policies.
-- Use the service-role key only on the server, never in Streamlit Cloud secrets exposed to users
-- or any client-side JavaScript. Add authenticated staff access policies before production use.
