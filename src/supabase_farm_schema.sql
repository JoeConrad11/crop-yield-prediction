-- Phase 1 of the farmer-app roadmap (see ../ARCHITECTURE.md): farmer
-- identity + their own farms/fields, private and RLS-scoped -- a different
-- concern from supabase_schema.sql's public, unauthenticated pipeline
-- output (live_predictions / crop_profitability). Run this once in the
-- Supabase SQL editor, same project as supabase_schema.sql. Requires
-- Supabase Auth (email/magic-link) to already be enabled on the project --
-- it is, by default.

-- One row per authenticated user, keyed by their auth.users id. Holds
-- profile fields beyond what auth.users itself has; created on first
-- sign-in by the frontend (see frontend/lib/supabase-client.ts).
create table if not exists farmers (
    id uuid primary key references auth.users (id) on delete cascade,
    display_name text,
    created_at timestamptz not null default now()
);

-- A farmer can operate more than one farm (leased ground, family
-- operations, etc.) -- kept as its own table from day one so the schema
-- doesn't need a migration when that matters, even though Phase 1's UI
-- only ever shows a farmer one (auto-created) farm.
create table if not exists farms (
    id bigint generated always as identity primary key,
    farmer_id uuid not null references farmers (id) on delete cascade,
    name text not null,
    created_at timestamptz not null default now()
);

-- One row per field a farmer has drawn. `boundary` is a GeoJSON Polygon
-- (the exact shape Leaflet's draw interaction and Phase 2's ee.Geometry
-- both consume directly) stored as jsonb rather than a PostGIS geography
-- column, so this works on any Supabase project with zero extension setup.
-- `acres` is computed client-side at save time (see frontend/lib/geo.ts)
-- and stored, not recomputed on every read.
create table if not exists fields (
    id bigint generated always as identity primary key,
    farm_id bigint not null references farms (id) on delete cascade,
    name text not null,
    boundary jsonb not null,
    acres double precision,
    primary_crop text,
    created_at timestamptz not null default now()
);

create index if not exists idx_farms_farmer on farms (farmer_id);
create index if not exists idx_fields_farm on fields (farm_id);

-- RLS: every table here is private to the owning farmer, unlike
-- supabase_schema.sql's "public read" policies -- a farmer's field
-- boundaries and (eventually) yield history are commercially sensitive,
-- treat them like financial data (see ARCHITECTURE.md).
alter table farmers enable row level security;
alter table farms enable row level security;
alter table fields enable row level security;

drop policy if exists "own profile" on farmers;
create policy "own profile" on farmers
    for all
    using (auth.uid() = id)
    with check (auth.uid() = id);

drop policy if exists "own farms" on farms;
create policy "own farms" on farms
    for all
    using (auth.uid() = farmer_id)
    with check (auth.uid() = farmer_id);

drop policy if exists "own fields" on fields;
create policy "own fields" on fields
    for all
    using (exists (
        select 1 from farms
        where farms.id = fields.farm_id and farms.farmer_id = auth.uid()
    ))
    with check (exists (
        select 1 from farms
        where farms.id = fields.farm_id and farms.farmer_id = auth.uid()
    ));
