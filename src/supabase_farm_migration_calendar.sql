-- Smart farm calendar (see ../ARCHITECTURE.md and src/farm_calendar.py).
-- ADDS three tables; touches nothing that already exists. Idempotent, so it
-- is safe to run more than once. Run in the Supabase SQL editor, after
-- supabase_farm_schema.sql (needs `farms`).
--
-- The calendar's due dates are DERIVED on demand (POST /calendar/plan) from
-- what is stored here plus the cited knowledge files, so nothing below
-- stores a computed schedule -- only what the farmer told us, and what they
-- have ticked off.

-- Livestock groups. A "herd" is any group tracked together (a cow-calf
-- herd, a flock of ewes); head_count is informational.
create table if not exists herds (
    id bigint generated always as identity primary key,
    farm_id bigint not null references farms (id) on delete cascade,
    species text not null check (species in ('cattle', 'sheep')),
    name text not null,
    head_count integer check (head_count is null or head_count >= 0),
    notes text,
    created_at timestamptz not null default now()
);

-- Anchor dates the schedules hang off: "lambed", "breeding_start",
-- "purchased", ... subject_id points at a fields.id or herds.id depending
-- on subject_type (polymorphic, so no foreign key -- ownership is enforced
-- through farm_id, and a field's planting date stays in fields.planting_date
-- rather than being duplicated here).
create table if not exists farm_events (
    id bigint generated always as identity primary key,
    farm_id bigint not null references farms (id) on delete cascade,
    subject_type text not null check (subject_type in ('field', 'herd')),
    subject_id bigint not null,
    kind text not null,
    event_date date not null,
    created_at timestamptz not null default now()
);

-- "Done" ticks. One row per (subject, rule, occurrence) so a repeating
-- item is completed one occurrence at a time, and completion survives the
-- schedule being recomputed.
create table if not exists calendar_completions (
    id bigint generated always as identity primary key,
    farm_id bigint not null references farms (id) on delete cascade,
    subject_type text not null check (subject_type in ('field', 'herd')),
    subject_id bigint not null,
    rule_id text not null,
    occurrence_date date not null,
    done_at timestamptz not null default now(),
    note text,
    unique (farm_id, subject_type, subject_id, rule_id, occurrence_date)
);

create index if not exists idx_herds_farm on herds (farm_id);
create index if not exists idx_farm_events_farm on farm_events (farm_id);
create index if not exists idx_calendar_completions_farm on calendar_completions (farm_id);

-- Same RLS pattern as `fields`: a row is visible/writable only to the
-- farmer who owns its farm.
alter table herds enable row level security;
alter table farm_events enable row level security;
alter table calendar_completions enable row level security;

drop policy if exists "own herds" on herds;
create policy "own herds" on herds
    for all
    using (exists (select 1 from farms where farms.id = herds.farm_id and farms.farmer_id = auth.uid()))
    with check (exists (select 1 from farms where farms.id = herds.farm_id and farms.farmer_id = auth.uid()));

drop policy if exists "own farm events" on farm_events;
create policy "own farm events" on farm_events
    for all
    using (exists (select 1 from farms where farms.id = farm_events.farm_id and farms.farmer_id = auth.uid()))
    with check (exists (select 1 from farms where farms.id = farm_events.farm_id and farms.farmer_id = auth.uid()));

drop policy if exists "own calendar completions" on calendar_completions;
create policy "own calendar completions" on calendar_completions
    for all
    using (exists (select 1 from farms where farms.id = calendar_completions.farm_id and farms.farmer_id = auth.uid()))
    with check (exists (select 1 from farms where farms.id = calendar_completions.farm_id and farms.farmer_id = auth.uid()));
