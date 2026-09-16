# Crop Yield Prediction

## Project Goal

Build a **predictive front-end web app that gives local farmers actionable
insights into which crops will perform best in their area**, based on
current-season conditions (satellite, weather, soil) combined with
historical yield, price, and cost records.

**Current stage: proof of concept at the county level.** Corn, soybeans, and
wheat, 4 states (IA, IL, NE, NC — wheat only covers IL/NE/NC, see "Known
limitations"), 2010–2025 historical + live current-season inference.
**Long-term direction: scale toward more granular geography**
(ideally field/farm level, not just county) **and more crops**, while
keeping the underlying pipeline honest about its limitations (regional cost
approximations, no crop-rotation logic, MODIS/CDL resolution limits) as it
moves from a research pipeline toward a real farmer-facing product. See
"Known limitations / open questions" below for the specific gaps standing
between where this is now and that goal.



## Status

Working end-to-end pipeline: fetch → merge → model → live-predict → compare crops.

- **Yield labels**: USDA NASS QuickStats, county-level, corn + soybeans +
  winter wheat (Iowa has zero county-level wheat yield data in any year
  checked -- excluded from wheat entirely, not just missing predictions).
- **NDVI**: MODIS (MOD13Q1), masked per-crop via the USDA Cropland Data
  Layer (CDL code 1=corn, 5=soybeans, 24=winter wheat), fetched per growing-season month
  (Jun/Jul/Aug) so the model sees a trajectory, not one flat average.
- **Weather**: PRISM (precip, tmin/tmax/tmean) via GEE `OREGONSTATE/PRISM/ANd`.
- **Soil moisture**: ERA5-Land reanalysis (chosen over NASA SMAP, which has
  no data before April 2015 and would've left 2010-2014 blank).
- **Soil**: OpenLandMap (organic carbon, pH, clay%, sand%, water capacity).
- **Terrain**: SRTM elevation + slope.
- Weather/soil-moisture/soil/terrain are crop-agnostic and fetched once,
  reused for every crop; only yield labels and NDVI are crop-specific.
- **Checkpoints**: `early_season` (Jun+Jul, in-season forecast) and
  `pre_harvest` (Jun+Jul+Aug, full season).
- **Best results** (Gradient Boosting, pre-harvest, leave-one-year-out CV):
  corn MAE ≈13 bu/acre, R² ≈0.75; soybeans MAE ≈4 bu/acre, R² ≈0.80
  (comparable ~8% relative error for both once yield scale is accounted for);
  wheat MAE ≈10 bu/acre, R² ≈0.14 -- meaningfully weaker, see "Known limitations".
- **Feature approach is chosen per crop/checkpoint, not fixed**: engineered
  features (county-trend detrending + NDVI/weather anomalies,
  `feature_engineering.py`) proved out for corn/soybean and are used
  everywhere for them, but actively hurt wheat/pre_harvest specifically
  (median R² went negative vs. baseline's +0.14) -- not enough per-county
  history in wheat's much smaller dataset to fit a reliable trend line. See
  `feature_engineering.best_variant()`, which every training/prediction/
  backtest script defers to rather than assuming engineered always wins.
- **Live inference**: `predict_live.py` pulls the current, in-progress
  season's data (as much as has actually elapsed) and predicts with the
  checkpoint model that matches — a query in June only sees June, so it
  uses `early_season`; once August completes it upgrades to `pre_harvest`.
  CDL for the current year isn't published until after harvest, so the
  crop mask falls back to the most recent available CDL year.
- **Crop comparison**: `compare_crops.py` converts each crop's predicted
  yield into predicted profit/acre (yield × NASS price − USDA ERS regional
  cost-of-production) and flags which crop has the edge per county. This
  flipped hard once cost data was added (corn: 306→14 counties favored,
  soybeans: 6→298) — plausible given documented negative corn margins in
  the current farm economy, but still missing crop-rotation logic.

## Project structure

```
crop-yield-prediction/
├── data/
│   ├── raw/          # untouched API/GEE pulls (never edit in place)
│   ├── processed/    # merged, model-ready tables, live predictions, comparisons
│   └── external/     # reference shapefiles, boundaries, lookup tables
├── notebooks/         # exploration, SHAP analysis
├── models/             # persisted production models (gb_<crop>_<checkpoint>.joblib)
├── src/
│   ├── config.py            # states, years, periods, checkpoints, CROPS registry
│   ├── fetch_nass.py         # yield labels, per crop, multi-state
│   ├── fetch_gee.py          # NDVI, crop-masked via CDL, per month
│   ├── fetch_prism.py        # weather, per month (crop-agnostic)
│   ├── fetch_soil_moisture.py  # ERA5-Land soil moisture, per month (crop-agnostic)
│   ├── fetch_soil.py         # OpenLandMap soil properties, static (crop-agnostic)
│   ├── fetch_terrain.py      # SRTM elevation/slope, static (crop-agnostic)
│   ├── fetch_prices.py       # NASS state-level commodity prices
│   ├── fetch_costs.py        # USDA ERS regional cost-of-production
│   ├── build_dataset.py      # merges + pivots into per-crop checkpoint tables
│   ├── model_utils.py        # shared model defs + leave-one-year-out eval
│   ├── train_models.py       # baseline model x checkpoint comparison, per crop
│   ├── feature_engineering.py  # detrending + anomaly features, A/B vs baseline
│   ├── train_final_models.py  # trains + persists production models
│   ├── predict_live.py       # live in-season prediction, per crop
│   └── compare_crops.py      # per-county profit comparison across all CROPS
└── references/         # papers, docs, data dictionaries
```

`data/` and `.venv/` stay out of git — see `.gitignore`. Keep raw pulls
immutable; all transforms happen on the way into `processed/`.

## Related repos

- **`ag-data-explorer`** (sibling directory, `../ag-data-explorer`) — "The
  Harvest Ledger," a separate, publicly-deployed Next.js site that reads
  this repo's historical output (via `scripts/seed.ts`, into its own
  Supabase project) and presents it as a static, editorial "what actually
  happened" record. No model, no prediction, no live backend — the opposite
  concern from this repo. The main dashboard's "The Harvest Ledger" button
  links out to it (`NEXT_PUBLIC_DATA_EXPLORER_URL` in `frontend/.env.local`,
  defaults to its Vercel deployment). See `ARCHITECTURE.md` for how it fits
  alongside the farmer-app direction.

## Environment

- `.env` holds `NASS_API_KEY` and `GEE_PROJECT_ID` (see `.env.example`).
- Google Earth Engine auth is local, not in `.env`: run
  `.venv/bin/earthengine --project=<id> authenticate` once per machine.
- All fetch/build/train scripts run from the project root with
  `.venv/bin/python3 src/<script>.py`.

## Pipeline order

Historical (run once, or to add a state/crop/year): all scripts accept crop
name(s) as args, e.g. `fetch_nass.py corn soybeans` (defaults to all crops
in `config.CROPS` if omitted). Currently 2010-2025 (`config.YEAR_END`).

1. `fetch_nass.py` → `data/raw/nass_<crop>_yield_multistate.csv`
2. `fetch_gee.py` → `data/raw/gee_ndvi_<crop>_periods.csv`
3. `fetch_prism.py`, `fetch_soil_moisture.py`, `fetch_soil.py`,
   `fetch_terrain.py` → crop-agnostic, run once regardless of crop count
4. `fetch_rotation.py` → `data/raw/rotation_<crop>.csv` (crop-specific;
   pct_continuous, CDL year-over-year, see "Crop rotation" below)
5. `build_dataset.py` → `data/processed/model_table_<crop>_<checkpoint>.csv`
6. `train_models.py` → baseline model comparison
7. `feature_engineering.py` → detrending/anomaly A/B comparison
8. `train_final_models.py` → persists `models/gb_<crop>_<checkpoint>.joblib`
   **on the engineered features** (detrend + anomaly), not raw ones — proven
   to help in step 7's comparison, see `docs`/session history for the numbers
9. `backtest_recent_years.py` → replays what each checkpoint would have
   predicted for the most recent real, completed seasons, as a trust check
10. `notebooks/` → SHAP feature-importance analysis

Live (run anytime during the season, or on a schedule via `modal_app.py`):

1. `fetch_prices.py`, `fetch_costs.py`, `fetch_price_paid_index.py` →
   latest price/cost lookups (the last one escalates ERS's stale cost
   estimate to a current-period equivalent, see "Cost/price" below)
2. `predict_live.py [crop ...]` → `data/processed/live_prediction_<crop>_<date>.csv`
   (applies the same detrend/anomaly transforms as training, via the
   `*_aux.joblib` artifacts `train_final_models.py` persists)
3. `compare_crops.py` → `data/processed/crop_comparison_<date>.csv`
4. `run_pipeline.py` → runs 2+3 and writes to Supabase (what the Modal cron calls)

## Frontend

`api/` (FastAPI, read-only, reads Supabase with the anon key) + `frontend/`
(Next.js) serve the pipeline's output as an interactive county map. Crop
metadata is entirely driven by `src/config.py` `CROPS` — no crop name is
hardcoded in either layer, so adding a crop to `CROPS` (plus its upstream
data) needs zero frontend/API changes.

- `api/main.py`: `GET /crops`, `GET /predictions[/latest]`,
  `GET /comparisons` (pivots `crop_profitability` into a per-county
  `best_crop`/`margin_dollars` shape), `GET /predictions/history` (year-by-
  year actual yield from `model_table_<crop>_pre_harvest.csv`, for the trend
  chart), `GET /geo/counties` (static GeoJSON built once via
  `api/scripts/build_county_geojson.py`).
- `frontend/`: a choropleth map (gray US-states backdrop, two-color gold-to-
  green yield gradient, zoom/pan, keyboard-accessible) over a searchable/
  sortable county comparison list. Click a county for a 4-tab dialog: yield
  trend + confidence band, a SHAP-based "why this prediction" breakdown
  (`api/routers/explain.py`, real per-instance feature attribution against
  the exact row `predict_live.py` used, not global importance), model
  accuracy (true held-out predicted-vs-actual across 2010-2025, not just the
  live model's own claim), and a crop-comparison trend (each crop indexed to
  its own county average, since raw bu/acre isn't comparable across crops).
  Design system at `frontend/design-system/crop-yield-predictor/MASTER.md`.
- Run locally: `.venv/bin/uvicorn api.main:app --port 8000` and
  `npm run dev --prefix frontend` (needs `frontend/.env.local` with
  `NEXT_PUBLIC_API_BASE_URL`, and `api/.env` with `SUPABASE_ANON_KEY` — see
  the `.env.example` files). Not yet deployed anywhere; local dev only.

## Known limitations / open questions

- NC's growing season runs ~3-4 weeks ahead of IA/IL/NE (earlier planting
  and harvest). Monthly checkpoints (Jun/Jul/Aug) are shared across all
  states for now — a state-specific calendar offset is a candidate
  follow-up if NC behaves very differently in the results.
- Counties below a crop-pixel-coverage threshold (see `MIN_CROP_PIXELS` in
  `build_dataset.py`) are dropped so NDVI isn't diluted by non-crop land.
- **Crop rotation**: `pct_continuous` (fraction of this year's crop pixels
  that were the same crop last year, from CDL year-over-year) is a real
  model input now, not ignored — but its effect is modest (~7 bu/acre for a
  highly-continuous county in one check), well below price/cost effects on
  `compare_crops.py`'s recommendation. Don't expect it to be the dominant
  factor in which crop the tool favors.
- **Cost/price**: `compare_crops.py` costs are USDA ERS **region**-level
  (Nebraska approximated as entirely "Northern Great Plains" though it spans
  two ERS regions), and the stale cost-basis-year problem is now corrected
  (not just flagged) by escalating via NASS's "PRODUCTION ITEMS - INDEX FOR
  PRICE PAID". That correction widened, not narrowed, the corn/soybean gap
  in one check — soybean prices have genuinely risen faster than corn's
  recently, a real market signal, not a pipeline artifact.
- **Wheat is real but meaningfully weaker than corn/soybean**: only 41
  counties total (vs. ~300 each for corn/soybean), and heavily NE-weighted
  (341 of 364 training rows) since most IL/NC counties don't clear
  `MIN_CROP_PIXELS` for wheat specifically even though NASS publishes
  county-level wheat yield for them. R² tops out around 0.14 (pre_harvest)
  vs. corn/soybean's usual 0.7-0.8, and year-to-year backtest R² swings wildly
  (-2.9 to +0.6) for some counties. Also: winter wheat's real season
  (fall-planted, harvested by early summer) doesn't line up with the
  Jun/Jul/Aug PERIODS/CHECKPOINTS built for corn/soybean's summer season --
  by the "pre_harvest" checkpoint, wheat is likely already harvested in
  reality. A wheat-specific season calendar is a candidate follow-up, same
  category as the NC calendar note above.
- **2025 backtest anomaly**: the corn model backtested notably worse for
  2025 (R² ~0.57-0.59 vs. the usual ~0.68-0.75), and pre-harvest didn't
  outperform early-season as it normally should. 2025's weather/NDVI/soil-
  moisture features were within 0.5-1.4 std of the historical range (not an
  extrapolation case) — the divergence looks like a real deviation between
  observed conditions and yield outcome that the current feature set
  doesn't explain (possible causes: a late-season event past August,
  disease/pest pressure, or management changes tied to the negative farm
  margins found in the ERS cost data). Documented, not yet resolved.
- Everything is **county-level**, not field-level — an individual farm can
  differ substantially from its county average. Getting to true farm-level
  precision needs field-boundary input + higher-resolution imagery
  (Sentinel-2, not MODIS) — see Project Goal above.
- Frontend (see "Frontend" above) is local-dev only — not deployed, no
  auth, CORS open to any localhost port for dev convenience. A full mobile-
  responsive pass and real hosting are still open.

## Data sources reference

### Yield labels
- **USDA NASS QuickStats API** — https://quickstats.nass.usda.gov/api
- **USDA NASS Crop Progress reports** — weekly % planted/emerged/harvested,
  useful for refining season checkpoint dates per state.

### Satellite / remote sensing
All pulled via **Google Earth Engine** (https://earthengine.google.com)
rather than raw file downloads:
- **NDVI** — MODIS `MODIS/061/MOD13Q1` (250m, 16-day composite).
- **Cropland Data Layer** — `USDA/NASS/CDL`, masks pixels per crop.
- **Soil moisture** — ERA5-Land `ECMWF/ERA5_LAND/DAILY_AGGR` (reanalysis,
  chosen over NASA SMAP because SMAP has no data before April 2015).
- **Soil properties** — OpenLandMap `OpenLandMap/SOL/...` layers (organic
  carbon, pH, clay%, sand%, water capacity).
- **DEM elevation/slope** — USGS `USGS/SRTMGL1_003`.

### Weather
- **PRISM** via GEE `OREGONSTATE/PRISM/ANd` (daily, 4km, CONUS). The older
  `OREGONSTATE/PRISM/AN81d` asset is deprecated and stops updating after
  ~2020 — use `ANd`.

### Prices and costs
- **NASS QuickStats "Price Received"** — state-level, monthly, $/bu.
- **USDA ERS Commodity Costs and Returns** — https://www.ers.usda.gov/data-products/commodity-costs-and-returns
  — no API, static CSV per commodity, published by farm-resource region
  (not state). `fetch_costs.py` downloads directly from `ers.usda.gov/media/...`.

### Not yet integrated
- **True gSSURGO** (vs. the OpenLandMap proxy currently used) —
  https://websoilsurvey.nrcs.usda.gov — no clean REST API.
- **Sentinel-2** (10m) — needed for field-level precision beyond MODIS's 250m.
