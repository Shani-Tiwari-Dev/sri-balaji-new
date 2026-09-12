-- Sri Balaji Granites & Marbles — reference schema for Supabase (Postgres)
-- Optional: running the Flask app with DATABASE_URL set will auto-create
-- these tables via SQLAlchemy on first run. Use this file only if you'd
-- rather create them by hand in the Supabase SQL editor first.

create extension if not exists "uuid-ossp";

create table if not exists public.slabs (
  id text primary key default uuid_generate_v4()::text,
  godown_id text not null,
  godown_name text not null,
  block_number text,
  title text not null,
  category text not null,
  image_url text,
  length numeric not null,
  width numeric not null,
  unit text not null default 'feet',
  pieces integer not null default 1,
  total_sq_ft numeric not null default 0,
  total_sq_meters numeric not null default 0,
  thickness_mm numeric,
  finish text,
  price_per_sq_ft numeric not null default 0,
  is_sold boolean not null default false,
  lot_name text,
  created_at timestamptz not null default now()
);

create table if not exists public.trash_items (
  id text primary key default uuid_generate_v4()::text,
  slab_snapshot jsonb not null,
  deleted_at timestamptz not null default now(),
  deleted_by text,
  expires_at timestamptz
);

create table if not exists public.customer_queries (
  id text primary key default uuid_generate_v4()::text,
  order_number text,
  client_name text not null,
  mobile_number text not null,
  delivery_address text,
  preferred_godown text default 'any',
  requirement text,
  dimension_unit text default 'feet',
  requested_quantity_sqft numeric default 0,
  selected_slabs jsonb default '[]',
  total_estimated_cost numeric,
  status text default 'Pending',
  created_at timestamptz not null default now(),
  notes text
);

create table if not exists public.announcements (
  id text primary key default uuid_generate_v4()::text,
  title text not null,
  message text not null,
  is_active boolean default true,
  type text default 'general',
  date text
);

-- Row Level Security: public read for catalog data, public insert for
-- enquiries; tighten the "full access" policies per staff role before
-- going live (see README "Security" section).
alter table public.slabs enable row level security;
alter table public.announcements enable row level security;
alter table public.customer_queries enable row level security;
alter table public.trash_items enable row level security;

create policy "Public read slabs" on public.slabs for select using (true);
create policy "Public read active announcements" on public.announcements for select using (true);
create policy "Public insert enquiries" on public.customer_queries for insert with check (true);

-- Permissive full-access policies for the service role used by the Flask
-- backend (which connects directly via DATABASE_URL, not the anon key).
create policy "Service full access slabs" on public.slabs for all using (true) with check (true);
create policy "Service full access trash" on public.trash_items for all using (true) with check (true);
create policy "Service full access queries" on public.customer_queries for all using (true) with check (true);
create policy "Service full access announcements" on public.announcements for all using (true) with check (true);
