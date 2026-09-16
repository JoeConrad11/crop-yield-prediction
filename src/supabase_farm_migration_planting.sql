-- Phase 4b, low-effort tier (see ../ARCHITECTURE.md): let a farmer tell us
-- what they actually planted and when. Run this once in the Supabase SQL
-- editor, same project as supabase_farm_schema.sql. Safe to re-run.
--
-- Why this is the highest-priority item on the roadmap despite being the
-- smallest, per ARCHITECTURE.md's "Re-evaluated sequencing":
--
-- 1. It removes real guessing that is happening today. The crop mask is
--    derived from USDA CDL, which is published a year late, so the live
--    path falls back to the previous year's classification. On a field
--    that rotates -- i.e. most fields -- that is simply wrong, and it was
--    hit in live testing: the app had to try corn, then soybeans, blind,
--    on a field whose CDL composition turned out to be 50% soybeans and
--    41% alfalfa. A farmer answering "soybeans, planted May 12" is both
--    cheaper and more accurate than any inference from imagery.
--
-- 2. `planting_date` is the single missing input for growth-stage
--    modelling. Growing Degree Days accumulate FROM PLANTING, and every
--    other ingredient (daily PRISM Tmax/Tmin) is already fetched. Without
--    it the pipeline is stuck slicing the season into fixed calendar
--    months, which smears the stage-specific windows where yield is
--    actually determined (corn pollination being the textbook case).
--
-- 3. It sharpens the small-farm monitoring product, which is what those
--    farmers get instead of a yield number: comparing a field to its own
--    history at the same GROWTH STAGE is agronomically correct, where
--    comparing at the same calendar week silently penalises a season that
--    was planted two weeks late.

alter table fields add column if not exists planting_date date;

-- Free-text, not an enum: crop identity everywhere else in this project is
-- whatever is in src/config.py CROPS (see api/models.py's note), so a new
-- crop must never require a schema migration.
comment on column fields.primary_crop is
    'Crop the farmer says is planted this season (matches an id in src/config.py CROPS). '
    'Farmer-reported and authoritative -- preferred over the CDL-derived guess, which is a '
    'year stale and wrong on rotated fields.';

comment on column fields.planting_date is
    'Farmer-reported planting date. Origin for Growing Degree Day accumulation and therefore '
    'for growth-stage-aware features and same-stage year-over-year comparison.';
