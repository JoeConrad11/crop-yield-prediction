-- Run this once in the Supabase SQL editor to create the tables the
-- scheduled pipeline writes into and the future frontend reads from.

create table if not exists live_predictions (
    id bigint generated always as identity primary key,
    as_of_date date not null,
    crop text not null,
    year int not null,
    state_fips text not null,
    county_fips text not null,
    county_name text not null,
    checkpoint text not null,
    predicted_yield_bu_acre double precision not null,
    predicted_yield_low double precision,
    predicted_yield_high double precision,
    confidence_mae double precision,
    coverage_tier text,
    crop_pixel_coverage double precision,
    historical_avg_yield double precision,
    delta_vs_historical double precision,
    pct_vs_historical double precision,
    created_at timestamptz not null default now(),
    unique (as_of_date, crop, state_fips, county_fips)
);

-- Long/tidy format: one row per (as_of_date, crop, state_fips, county_fips).
-- Replaces the old wide `crop_comparisons` table (corn_*/soybeans_* column
-- pairs), which couldn't accommodate a third crop without a schema change.
-- "Which crop wins for this county" is now a read-time computation (idxmax
-- over profit_per_acre across whichever crops are present) instead of a
-- persisted binary field -- see src/compare_crops.py.
create table if not exists crop_profitability (
    id bigint generated always as identity primary key,
    as_of_date date not null,
    crop text not null,
    year int not null,
    state_fips text not null,
    county_fips text not null,
    county_name text not null,
    state_alpha text not null,
    yield_bu_acre double precision,
    price_per_bu double precision,
    cost_per_acre double precision,
    revenue_per_acre double precision,
    profit_per_acre double precision,
    -- cost escalation (see fetch_price_paid_index.py) -- cost_per_acre above
    -- is the ESCALATED (corrected) figure; these are the raw inputs to that
    ers_basis_cost_per_acre double precision,
    cost_escalation_ratio double precision,
    -- secondary transparency/sanity-check columns (see fetch_costs.py docstring)
    cost_basis_year int,
    ers_basis_price_per_bu double precision,
    price_vs_ers_basis_pct double precision,
    ers_baseline_net_value double precision,
    created_at timestamptz not null default now(),
    unique (as_of_date, crop, state_fips, county_fips)
);

create index if not exists idx_live_predictions_as_of on live_predictions (as_of_date);
create index if not exists idx_crop_profitability_as_of on crop_profitability (as_of_date);

-- Public read access for the FastAPI service (uses the anon key, not the
-- service-role key the Modal cron writes with).
alter table live_predictions enable row level security;
alter table crop_profitability enable row level security;

drop policy if exists "public read" on live_predictions;
create policy "public read" on live_predictions for select using (true);

drop policy if exists "public read" on crop_profitability;
create policy "public read" on crop_profitability for select using (true);

-- One-time cleanup: drop the old wide table now that compare_crops.py /
-- supabase_writer.py write to crop_profitability instead. POC-stage data,
-- fully recomputable via run_pipeline.py -- no migration needed.
drop table if exists crop_comparisons;
