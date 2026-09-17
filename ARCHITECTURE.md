# Architecture

## System map

Two repos today, each with a deliberately different job:

- **`crop-yield-prediction`** (this repo) — the predictive engine. Fetches
  satellite/weather/soil data, trains checkpoint models per crop, serves
  live county-level predictions + crop-comparison via FastAPI, and renders
  them as an interactive map (`frontend/`). This is where the farmer-facing
  product grows from.
- **`ag-data-explorer`** (sibling directory) — "The Harvest Ledger." A
  separate, publicly-deployed, read-only Next.js site that reads this
  repo's historical output into its own Supabase project and presents it
  editorially. No model, no live backend, no auth. Exists so the historical
  record has a home that doesn't have to carry prediction-app concerns
  (auth, personalization, live inference) and vice versa. Linked from this
  repo's dashboard header, not embedded.

Keep that split. Personalized/farmer-account work belongs in
`crop-yield-prediction`, not `ag-data-explorer` — the moment a farmer's
private field/yield data enters the picture, "no backend, public read-only"
stops being true, and that's a different product with different privacy
obligations.

## The core constraint driving the farmer-app design

USDA NASS county-level yield surveys are the model's only ground truth —
**there is no public field-level yield label**. This means "field-level
prediction" can mean two different things, and every feature built on top
of it must be honest about which:

1. **Field-level *input*, county-calibrated *model*** — pull NDVI/weather/
   soil for the farmer's actual field polygon instead of the county
   average, but run it through a model still fundamentally fit on
   county-level yield behavior. Frame this to the farmer as "how your
   field's conditions compare to the county trend," never as an exact
   bushels/acre guarantee.
2. **Farmer-calibrated** — once a farmer contributes their own historical
   yield (combine monitor, elevator receipts, FSA records), use it as a
   bias-correction on top of (1). This is what actually earns
   "personalized," and it's a trust/data-collection problem, not a
   modeling one — it only becomes available after a farmer already trusts
   the app enough to hand over their numbers.

Build (1) first. Design the UI/copy so upgrading to (2) later doesn't
require walking back an overpromise made in (1).

## Phased roadmap: county tool → personalized farmer product

**Phase 1 — Farm/field identity layer** *(done)*
Farmer accounts + a `farms`/`fields` data model (field = polygon geometry +
crop history), scoped to the owning farmer via Supabase RLS. This is the
one piece everything else is blocked on — no personalization is possible
without a field to point at. Verified end to end: sign in, draw a field on
free Esri satellite tiles, save, survives reload, delete.

**Phase 2 — Field-level data pipeline** *(done)*
Generalized `fetch_gee.py` / `fetch_prism.py` / `fetch_soil_moisture.py` /
`fetch_soil.py` / `fetch_terrain.py` / `fetch_rotation.py` from FIPS-county
geometries to arbitrary farmer-drawn polygons (`ee.Geometry` doesn't care
which) via `src/fetch_field_features.py`. Two real Earth Engine bugs found
and fixed along the way (`reduceRegion` band-prefixes combined-reducer
output keys unlike `reduceRegions`; ERA5-Land silently returns `None` at
its native ~11km scale over a field-sized polygon) — see git history on
`fetch_gee.py`/`fetch_soil_moisture.py` for the details.

**Phase 3 — Personalized prediction & recommendation** *(done)*
Applied the existing checkpoint models to field-level features (constraint
(1) above, clearly labeled) via `src/predict_field.py` and
`POST /fields/predict`. A field's state/county is resolved automatically
by a spatial join against `TIGER/2018/Counties` (`fetch_field_features.
field_county()`) — no manual state picker needed. A farmer draws a field,
picks a crop, clicks "Predict my field," and gets a live number with an
honest "vs. your county" framing, a confidence range, and a coverage tier.
Extending `compare_crops.py`'s profit comparison to use the farmer's own
input costs, and collecting farmer-provided yield history (constraint (2)),
did not happen here — folded into Phase 4 below, since both turn out to be
the same underlying need (a farmer-input data layer) as the small-field
coverage problem Phase 3 surfaced.

**Phase 4 — Field-scale data resolution** *(in progress — 4a built but
blocked on calibration, coverage-tier fix done, 4b not started)*
Phase 3 surfaced a real physical limit, not a software bug: MODIS NDVI (the
crop-health signal) is 250m/pixel (~15.4 acres/pixel). A field under
roughly 40-60 acres can easily contain zero fully-inside MODIS pixels, so
`crop_pixel_coverage` comes back 0 and the prediction can't run at all —
confirmed live while browser-testing Phase 3 (several small/irregular test
polygons near Ames, IA came back `insufficient_coverage` for both corn and
soybeans). Weather (PRISM/ERA5, already ~4-11km) and soil (SoilGrids,
~250m) are NOT part of this problem — those are legitimately regional
signals even at true field scale, so a coarse pixel there isn't "wrong,"
it's honest. NDVI is different: it's supposed to read *this* field's crop
health, and at 250m it mostly can't below a certain field size. This phase
has two independent halves — do (a) first, it helps every field with zero
farmer effort; (b) is higher-value per field but needs farmer trust and time.

- **4a. Sentinel-2 NDVI (10m/pixel, same GEE pipeline).** *(built, but
  BLOCKED on the calibration finding below — do not ship as-is)* Swap
  `fetch_period_ndvi_for_field`'s source from `MODIS/061/MOD13Q1` to
  `COPERNICUS/S2_SR_HARMONIZED`'s red/NIR bands — roughly 625x the pixel
  density of MODIS, so a 20-acre field goes from ~1 pixel to several
  hundred. Real work, not a one-line swap: Sentinel-2 needs its own
  cloud/shadow masking (`QA60` or the `s2cloudless` collection) and a
  per-period composite (median of cloud-free scenes), where MODIS's
  `.mean()` over a pre-cleaned 16-day composite product needed neither.
  Leave the COUNTY-level path (`fetch_period_ndvi`, and the trained models)
  on MODIS unchanged — retraining is out of scope here — only the
  field-level `_for_field` path switches. That creates a second, honest gap
  worth validating before trusting it: Sentinel-2 and MODIS are different
  sensors with different band responses and compositing, so feeding
  Sentinel-2 NDVI into a MODIS-calibrated model stacks a new approximation
  on top of constraint (1)'s existing one. Validate first — compute both
  NDVI sources for the same historical counties/years already in
  `data/processed/`, and check whether Sentinel-2 needs a linear correction
  toward MODIS's scale before its values feed a live prediction. Same
  rigor as the `reduceRegion`/`reduceRegions` key-prefix bug and the ERA5
  coarse-scale bug from Phase 2 — verify by hand before shipping.

- **4b. Farmer-submitted field data.** Two tiers, kept deliberately
  separate — very different cost and very different value:
  - *Low-effort*: confirmed crop + planting date on the `fields` row
    (`primary_crop` already exists and is empty today). Removes the blind
    corn-then-soybean guessing the CDL-based rotation mask currently forces
    on both the farmer and the code (also hit live while testing Phase 3),
    and lets checkpoint-picking key off the farmer's real planting date
    instead of a fixed calendar month.
  - *High-effort, high-value*: the farmer's own historical yield per field
    (a combine yield-monitor export, or just typed-in past-year numbers).
    This is the ONLY path to constraint (2) ("farmer-calibrated") from the
    core-constraint section above — no public field-level yield label
    exists anywhere else to build one from. Collect and store it here, but
    don't wire it into predictions yet — turning it into a bias-correction
    on top of the county-calibrated model is its own modeling decision (how
    many years of history before trusting a field's own trend over its
    county's?) that deserves its own pass once there's real data to look at.

### What 4a's validation actually found (2026-09, `src/validate_sentinel2_ndvi.py`)

Sentinel-2 fixes the coverage problem decisively, and simultaneously proved
that the planned linear correction onto MODIS's scale **cannot be shipped**.
Both halves of that matter; neither should be quietly dropped later.

*Coverage is solved.* On a real 18.8-acre farmer-drawn field in western
Iowa, soybean pixels went from **4 (MODIS) to 577 (Sentinel-2)** — the
difference between a statistically meaningless average and a usable one.

*But MODIS at field scale was measuring the wrong land.* That same field's
2025 CDL composition is 50.5% soybeans / 41.2% alfalfa / 0.9% corn (a
single 30m pixel). MODIS nonetheless returned **3 "corn" pixels at NDVI
0.82-0.89** — a confident-looking reading of a crop the field essentially
doesn't grow, pulled in from neighboring ground through its 250m grid.
Sentinel-2 correctly returned no corn. MODIS also showed that field's
soybean NDVI as flat and high across the whole season (0.861 / 0.879 /
0.884 for jun/jul/aug), which is agronomically impossible — June soybeans
are barely emerged. Sentinel-2 traced the actual emergence curve
(0.544 / 0.878 / 0.855). So at small-field scale MODIS is not merely
imprecise, it is describing different ground.

*And the correction doesn't fit.* Fitting `MODIS ~ a*S2 + b` on 890 paired
county observations (99 Iowa counties x 2019/2022/2024 x jun/jul/aug):

| fit | slope | r² |
|---|---|---|
| pooled | 0.331 | 0.716 |
| jun | 0.250 | 0.417 |
| jul | 0.106 | 0.082 |
| aug | 0.018 | **0.005** |

The pooled r²=0.716 is an **artifact of aggregation**, not a real
relationship: June clusters low and August clusters high, so pooling
manufactures correlation across period clusters while within any single
period the sensors barely track each other. The cause is visible in the
spread — MODIS's county-to-county standard deviation collapses from 0.055
(jun) to 0.023 (jul) / 0.028 (aug) while Sentinel-2 holds 0.063-0.142.
**MODIS saturates mid-season**: by July nearly every county pins near 0.86
and there is almost no dynamic range left to calibrate against. County
ranking agreement between the sensors is correspondingly unstable across
years (jul: +0.81, +0.07, +0.31; aug: +0.34, **-0.14**, +0.41).

Two consequences, one of them about code already in production:
1. Do not ship a linear S2→MODIS correction. It would have injected noise
   into every field prediction while looking respectable via the pooled r².
2. **This is also a finding about the existing county model.** If MODIS
   county NDVI has a spatial spread of ~0.02 in jul/aug, the `ndvi_jul` /
   `ndvi_aug` features may be carrying far less signal than assumed. Worth
   checking feature importances against this before trusting mid-season
   NDVI in the current production model.

### How the production model actually uses NDVI (measured, 2026-09)

Worth recording independently of Sentinel-2, because it was not previously
written down anywhere and it changes how any NDVI work should be evaluated.
Reading `feature_importances_` off the shipped models:

| feature | corn early | corn pre | soy early | soy pre |
|---|---|---|---|---|
| `anom_ndvi_jul` | **0.380** (#1) | **0.356** (#1) | **0.333** (#1) | **0.283** (#1) |
| `anom_ndvi_aug` | — | 0.041 | — | 0.128 (#2) |
| `ndvi_jul` (raw) | 0.008 (#23) | 0.003 (#38) | 0.007 (#31) | 0.008 (#24) |
| `ndvi_aug` (raw) | — | 0.003 (#41) | — | 0.021 |

**The model runs on NDVI anomalies, not NDVI levels.** The raw level
features are near-dead — consistent with MODIS's county-to-county spread
collapsing to ~0.02 by July — while the deviation from a county's own
historical mean is the single most important input in every corn and
soybean model. The between-county component (soil, geography) is already
carried by the static soil/terrain features; what NDVI contributes is the
year-specific departure.

Two consequences:
1. Any new NDVI source must be evaluated **in anomaly space**, and
   specifically on `jul`. Comparing absolute levels (as the original 4a
   correction plan did) measures something the model never consumes.
2. An absolute sensor offset should largely *cancel* inside an anomaly —
   which is why Sentinel-2 looked salvageable even after the level-based
   correction failed. It wasn't: sensor agreement in anomaly space is
   r=0.183 (jul) and **-0.107** (aug), worst exactly where the model leans
   hardest.

### The decision gate: agreement with real yield, not with MODIS

Sensor-vs-sensor correlation says whether two measurements agree, never
which is correct — and Sentinel-2 carries ~3x MODIS's anomaly spread, which
is either signal MODIS smooths away or contamination. Only NASS county
yield, the project's one ground truth, distinguishes those. Testing both
sensors' NDVI anomalies against county corn yield anomalies (773 paired
Iowa observations, 2019/2022/2024):

| period | MODIS vs yield | S2 (QA60) vs yield |
|---|---|---|
| jun | 0.566 | 0.446 |
| jul | **0.571** | 0.172 |
| aug | 0.186 | 0.102 |
| pooled | **0.430** | 0.250 |

MODIS wins in every period. Sentinel-2's extra spread was **noise, not
signal**, so retraining on it as-fetched would have produced a measurably
worse model. This test is now part of `validate_sentinel2_ndvi.py`
(`yield_signal_test`) and is the gate any future NDVI source must clear.

*Caveat on scale, so these findings aren't over-read:* this is a
COUNTY-scale result, where MODIS averages over large, mostly-pure crop area
and is trustworthy. It does not rehabilitate MODIS at FIELD scale, where it
demonstrably reads neighboring ground (the 0.9%-corn field above). Both
hold simultaneously.

*What it actually indicted was the compositing, not Sentinel-2.* The QA60
mask used for the numbers above misses haze and thin cirrus, and
Sentinel-2's early-2022 processing-baseline change left that band largely
empty on newer scenes — it degrades silently while appearing to work. The
masker has since been switched to **Cloud Score+**
(`GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`, `cs >= 0.6`), Google's current
best-practice for S2 in Earth Engine, and the yield gate re-run against it.
Path A stands or falls on that number.

### RESOLVED (2026-09): Path A refuted, a targeted hybrid is what the data supports

Re-running the yield gate with Cloud Score+ masking and a proper 8-year
sample (2018-2025, Iowa, n=2376) settled it. Both fixes mattered: QA60 →
Cloud Score+ recovered most of Sentinel-2's apparent deficit (pooled 0.250
→ 0.359 on the 3-year sample), and widening 3 → 8 years corrected badly
noisy anomaly estimates, moving August's correlation up for *both* sensors
(MODIS 0.175 → 0.390, S2 0.284 → 0.470).

Final agreement with real county corn yield, in anomaly space:

| period | MODIS | Sentinel-2 | winner |
|---|---|---|---|
| jun | 0.409 | 0.339 | MODIS |
| jul | **0.428** | 0.301 | MODIS |
| aug | 0.390 | **0.470** | **Sentinel-2** |
| pooled | **0.378** | 0.299 | MODIS |

**Path A (retrain wholesale on Sentinel-2) is refuted.** Sentinel-2 loses
June and July, and July is where the model's dominant feature lives
(`anom_ndvi_jul`, 0.28-0.38 importance). Retraining everything on S2 would
degrade the model — the earlier "S2 has more variance so it must have more
signal" intuition was wrong, and only the yield gate could show that.

**But August genuinely reverses, and it holds up.** Leave-one-year-out,
Sentinel-2 wins 7 of 8 folds (the 8th a tie: 0.507 vs 0.506); within
individual years it wins 6 of 8. In 2018 MODIS is actively *negative*
(-0.240) where S2 is +0.228. The mechanism is the same saturation seen
everywhere else in this analysis: by August the canopy is closed and MODIS
at 250m has no dynamic range left, while Sentinel-2 still discriminates.
Corroborating this, August is the one period where the two sensors' fitted
relationship is near 1:1 (slope 1.07, r²=0.575) — they agree on scale, they
disagree on which counties are doing well, and Sentinel-2 is the one that
matches yield.

**So the supported option is neither A nor B but a targeted hybrid: keep
MODIS for jun/jul, use Sentinel-2 for aug.** Honest sizing of the payoff
before anyone builds it — it is real but bounded, and lands in exactly one
place:
- `soybeans`/`pre_harvest`: `anom_ndvi_aug` is the **#2 feature (0.128)**,
  improving from r=0.39 to r=0.47. This is where the gain is.
- `corn`/`pre_harvest`: `anom_ndvi_aug` is only 0.041 (#5) — marginal.
- Both `early_season` models don't use August at all — **no change**.

It also means a mixed-sensor feature set, which has a real cost: the
pre_harvest models would need retraining, and any future NDVI change has to
re-clear the yield gate per period rather than once.

*Remaining caveat:* Iowa only. The mechanism (mid-season MODIS saturation)
should generalize to IL/NE, and NC's different calendar makes it the most
likely to behave differently. Worth re-running the gate across all four
states before shipping a mixed-sensor model.

**The two original paths, kept for context** (superseded by the hybrid
above; neither is a good choice on its own):
- **Path A — retrain the field-level model on Sentinel-2 features.** The
  only statistically sound way to put Sentinel-2 into a prediction. Build
  an S2 historical county dataset and retrain the checkpoint models on it,
  so features at inference come from the same sensor as features at
  training. Cost: Sentinel-2's usable record starts ~2018 (S2A mid-2015,
  S2B 2017, and composite quality depends on revisit frequency), so ~8
  training years vs MODIS's 16 — materially weaker leave-one-year-out CV.
  Offsetting that, S2 carries visibly more spatial signal (3-5x the
  variance), so the tradeoff is real but not obviously bad. This is a
  bigger project than 4a was scoped as.
- **Path B — keep the model on MODIS; use Sentinel-2 as farmer-facing
  information only.** Show the field's own true NDVI curve and its
  season-over-season change (which we now know MODIS cannot see at this
  scale), while the yield *number* stays explicitly county-level. Cheap
  and immediately useful, but it does not deliver a field-specific
  prediction, so it does not fully discharge the small-farm promise.

### Coverage confidence is measured in acres, not pixels *(done)*

`predict_live.coverage_tier()` tiers on raw pixel count against
`MIN_CROP_PIXELS` (500), which is a statement about MODIS at county scale
rather than about the field: the same ground measured by MODIS (15.4
acres/pixel) and Sentinel-2 (0.025 acres/pixel) differs ~625x in pixel
count. Field-level confidence therefore tiers on **observed crop acres**
(`fetch_field_features.field_coverage_tier`), which is invariant to sensor.

**Calibration correction (same session).** The first version refused any
field where one pixel covered >10% of it, which meant MODIS required a
154-acre field -- refusing 20, 40, 80 AND 110-acre fields, i.e. most real
US corn/soy fields and both of the project's own test fields. That was an
arbitrary cliff dressed as a measurement: the only *evidence* was at the
extreme (an 18.8-acre field, one pixel = 82% of it, MODIS reporting a crop
that wasn't there). Over-reach turned out not to discriminate by size at
all -- measured 1.23x on 113 acres, 1.36x on 228, 1.42x on 2731 -- so it
can't separate usable from unusable; only pixel-to-field size can.

Replaced with two lines, because the reality is a spectrum:
- **refuse above 33%** (MODIS: under ~47 acres) -- where a single pixel is
  a third or more of the field, which is the regime the measured failure
  sits in;
- **cap at "low" between 10% and 33%** (~47-154 acres) -- coarse but
  field-ish, so it answers with honest low confidence instead of nothing.

Only the far end is measured; the middle band is a judgement call that
deliberately errs toward a labelled answer over silence. With it, a real
109.7-acre Iowa field returns 192.4 bu/acre at `low` confidence rather than
being refused.

That change also made a previously-invisible failure explicit. A new
`unreliable` tier fires when the reported crop area exceeds the field's own
area — physically impossible, and the signature of a coarse sensor reading
neighboring ground. The 18.8-acre test field above reports 62 observed
acres of soybeans and 46 of corn, so it is now refused with an explanation
instead of receiving a number. **Before this, `predict_field()` returned a
confident 61.5 bu/acre for that class of field.** The guard discriminates
correctly rather than just being conservative: an identical 61.8 observed
acres scores `high` on a genuinely 227-acre field and `unreliable` on the
19-acre one.

**Phase 5 — Delivery & trust**
Mobile-first (a farmer isn't at a desktop) — PWA before native to keep cost
down. Checkpoint-based push/SMS/email at the same `early_season`/
`pre_harvest` boundaries the model already uses, instead of a dashboard to
remember to check. Surface the SHAP explanation (`api/routers/explain.py`
already exists) next to every number — explainability is the primary trust
lever for a farmer-facing yield number.

**Phase 6 — Production hardening**
RLS audit (a farmer's yield/field data is commercially sensitive — treat it
like financial data, not like the public county data this repo already
serves). ToS/privacy policy covering field-boundary and yield data use.
Real hosting/domain for `frontend/`, which is currently local-dev only.

## What a small farm can actually be told (the reliable product)

A yield number for a 20-acre field is not achievable today and saying so
plainly is better than shipping one: MODIS pixels are 15.4 acres, one pixel
covers ~82% of such a field, and Sentinel-2 — which *can* see the field —
was shown above to lose to MODIS against real yield in jun/jul, so it can't
carry the model either. Refusing (`unreliable_coverage`) is correct.

But refusing is not a product, and small farms are the stated target user.
The reframe: **the calibration problem was always cross-sensor. Comparing a
field to ITSELF over time never leaves Sentinel-2, so none of it applies.**
Same sensor, same polygon, same masking, ~1020 pixels on an 18.8-acre
field, every year. That comparison is apples-to-apples by construction and
needs no county model, no retraining, and no correction factor.

Demonstrated on the 18.8-acre test field (whole-field July NDVI, no crop
mask — the farmer already knows what they planted, so masking only adds
CDL's guessing):

| 2021 | 2022 | 2023 | 2024 | 2025 | **2026** |
|---|---|---|---|---|---|
| 0.866 | 0.806 | 0.775 | 0.823 | 0.808 | **0.672** |

Five-year mean 0.816, sd 0.033 — the current season sits **-4.3 standard
deviations** below the field's own history, -17.6% vs its own average. That
is a real, defensible, actionable alert on a field the yield model must
refuse. And it is arguably *more* useful than a point estimate: a farmer
can act on "your canopy is far below every one of the last five years,"
where "62 bu/acre ± 3.6" invites no action at all.

So the small-farm product is **field monitoring and relative benchmarking**,
not yield prediction. What is reliable at this scale, and why:

| Signal | Source | Why it's trustworthy here |
|---|---|---|
| Canopy vs the field's own history | Sentinel-2 10m, same polygon each year | same-sensor comparison; ~1020 px on 18.8 ac |
| Canopy vs nearby fields of the same crop | Sentinel-2, same date/sensor | same-sensor comparison, spatial instead of temporal |
| What is actually growing | CDL 30m | measured, verifiable — found the test field is 50.5% soybeans / 41.2% alfalfa |
| Terrain (slope, elevation) | SRTM 30m | ~85 px on 18.8 ac; static |
| Weather / stress context | PRISM 4km, ERA5 11km | genuinely regional; honest *as* regional context, not field-specific |

Deliberately excluded: a bushels/acre number, and anything derived from
MODIS at this scale.

Two things sharpen this later rather than blocking it now: **planting date
(4b)** turns "vs. the same calendar week" into "vs. the same growth stage,"
which is the agronomically correct comparison and removes year-to-year
planting-date noise from the baseline; and **the field's own accumulated
history** gets stronger every season the farmer stays.

### BUILT (2026-09): growth staging and same-stage benchmarking

Both of the sharpeners above now exist, because 4b collected the planting
date that unblocked them.

- `src/growth_stages.py` -- GDU thresholds and what they mean. Corn from
  Midwest extension guides (VE through R6). Soybeans marked
  `approximate` with the reason attached (development is substantially
  photoperiod-driven, not purely thermal). **Winter wheat deliberately
  absent**: it is fall-planted and overwinters, so heat-since-planting
  spans dormancy and doesn't describe development -- inventing thresholds
  there is the fabricated-agronomy failure this document warns against, so
  the API declines instead.
- `src/fetch_prism.py` -- `fetch_field_gdd()` (heat since planting) and
  `fetch_field_daily_gdu()` (the daily series, sampled at the field
  centroid because PRISM's 4km cell is larger than any field, which makes
  a multi-year series affordable in one round trip).
- `src/field_insights.py` + `POST /fields/stage`, `POST /fields/benchmark`.

Kept **separate from `/fields/predict` on purpose**: the yield endpoint
correctly refuses on fields too small to resolve, and these must stay
available to exactly those farmers. Staging depends only on temperature, so
field size is irrelevant to its quality.

Verified against real phenology -- corn planted 12 May near Ames gives V6 in
mid-June, silking 20-22 July, dent early September. And two fields at the
same location planted 12 May and 17 June correctly read R5 and R3 on the
same day, which is precisely the distinction fixed calendar months erase.

Two implementation notes worth keeping:
- **Composite windows widen adaptively** (+/-7, 14, 21 days). A fixed +/-7
  returned zero usable pixels for September 2026 on the test field while
  +/-14 returned 12,656 -- cloud genuinely empties narrow windows. The
  width actually used is reported, so a loosened comparison is visible
  rather than silent.
- **Prior seasons are assumed planted on the same month/day as the current
  one**, since only the current season's date is known. This is far closer
  than comparing calendar dates (each year still contributes its own
  temperature history, the dominant term), but it is an approximation and
  is surfaced in the response and the UI. Collecting a planting date each
  season retires it permanently.

## Bringing real agronomy in

Everything above is remote sensing and statistics. A farmer's trust —
and a meaningful accuracy gain — depends on the model also encoding how
crops actually grow. Agronomic knowledge enters at three distinct layers,
and conflating them is how a project like this starts inventing advice.

**Layer 1 — Growth stages instead of calendar months (feature engineering).**
The pipeline currently slices the season into fixed months (jun/jul/aug;
mar/apr/may for wheat). Crops do not grow on a calendar — they grow on
accumulated heat. The standard agronomic measure is **Growing Degree Days**
(corn: daily `mean(Tmax capped 86°F, Tmin floored 50°F) - 50°F`, accumulated
from planting), which maps onto real stages (corn V6 → VT/R1 silking → R5
dent; soybean R3 → R5 grain fill). This matters because **yield sensitivity
is wildly stage-dependent**: heat and moisture stress during corn
pollination (R1) is one of the best-established yield determinants in
agronomy, while identical stress three weeks earlier costs far less. Fixed
monthly windows smear that signal — a July mean blends pre- and
post-pollination for fields planted two weeks apart. Every input needed for
this is *already fetched* (daily PRISM Tmax/Tmin), with one missing piece:
the planting date, which is exactly what 4b collects.

**Layer 2 — Stress metrics instead of raw means (feature engineering).**
Monthly `tmean` is agronomically weak. Known mechanisms are threshold- and
timing-based, and encoding them injects domain knowledge the model would
otherwise have to learn from scratch on limited data: count of days above
~30°C during pollination, consecutive dry days during grain fill, excess
moisture at planting. These are established relationships, not patterns to
be discovered.

### RESOLVED (2026-09): Layer 2 evaluated, shipped on 2 of 6 checkpoints

Built the metrics above (`fetch_prism.fetch_period_stress`: `edd_29c`
Schlenker & Roberts extreme/killing degree days base 29°C, `gdd_10_30c`
beneficial heat, `days_above_30c`/`days_above_35c`, `dry_days`,
`heavy_rain_days`) and ran the same discipline as 4a's Sentinel-2 gate:
domain plausibility (the raw EDD signal is dramatic — Iowa July 2012
drought EDD=132 vs July 2014's record-yield EDD=8.5) is not evidence *this*
model gains anything, since it already has tmax/tmean/soil moisture and may
already capture the same variance by other means. `evaluate_stress_features.py`
ran identical leave-one-year-out CV with and without the stress columns, on
the engineered variant (the one actually shipped for corn/soy):

| crop/checkpoint | engineered MAE, without → with | verdict |
|---|---|---|
| corn/early_season | 14.315 → 14.129 (-0.186) | **real improvement** |
| soybeans/pre_harvest | 3.644 → 3.507 (-0.137) | **real improvement** |
| corn/pre_harvest | 13.663 → 13.689 (+0.025) | wash, noise-level |
| soybeans/early_season | 4.252 → 4.276 (+0.024) | wash, noise-level |
| wheat/early_season | 9.118 → 9.736 (+0.618) | clearly worse |
| wheat/pre_harvest | 9.447 → 9.038 (-0.410) | untrustworthy — R² still ~0 |

Result is a per-checkpoint pattern, not all-or-nothing: real, meaningful
gains landed only on the two largest/most reliable samples. Wheat moved in
both directions and got worse where the sample is largest (early_season),
consistent with the dormancy caveat already in `growth_stages.py` (winter
wheat's heat-since-planting spans dormancy, so a threshold metric computed
over that window is measuring something less coherent than it is for
corn/soybean). **Shipped: stress features included only in
`gb_corn_early_season` and `gb_soybeans_pre_harvest`** (`build_dataset.NEEDS_STRESS`
is the single source of truth train_final_models.py, predict_live.py, and
fetch_field_features.py all read, so the trained feature set and what gets
fetched live can't drift apart). The other four checkpoints keep their
prior feature set — added complexity that doesn't pay for itself isn't
shipped, same standard as 4a's Path A refutation above.

Shipping this also required live-fetch wiring that didn't exist before:
neither the county pipeline (`predict_live.py`) nor the field pipeline
(`fetch_field_features.py`) fetched *current-season* stress metrics at
all, only weather/NDVI/moisture. Without adding that, the two shipped
checkpoints would have silently zero-filled every stress feature at
prediction time via the existing `if col not in df.columns: df[col] = 0`
fallback (there for legitimate cases like an absent state dummy) — a
fabricated value masquerading as a real one, on exactly the checkpoints
meant to be more accurate. Added `predict_live.fetch_current_stress()` and
`fetch_prism.fetch_period_stress_for_field()`, both gated behind
`NEEDS_STRESS` so the extra GEE round trip is only paid on-demand for the
two checkpoints that actually need it.

**Side finding while regenerating the accuracy comparison**: rebuilding
`feature_engineering_comparison.csv` (needed anyway, so `confidence_mae`
shown to users reflects the corrected stress-inclusive accuracy) also
picked up current data for every other checkpoint. `wheat/early_season`'s
engineered variant is now median R²=-0.06 (was positive when the comparison
file was last generated, Sept 3, before several rounds of data changes) —
`best_variant()`'s existing rule (don't ship an R²<0 model over a
genuinely-positive alternative, same rule already applied to
wheat/pre_harvest) correctly flips it to baseline. Not a new policy, just
that rule firing on current numbers; flagged here since it's a real change
to what's shipped beyond this session's stress-feature scope.

**Layer 3 — Advice, sourced not invented (product).** A number becomes
useful when paired with what to do about it. The hard rule: **agronomic
advice must be traceable to a real source or to the model's own
explanation — never generated prose that merely sounds authoritative.**
Two legitimate sources exist here, and conveniently the land-grant
extension services for all four project states are exactly the right ones:
Iowa State, Illinois, Nebraska, and NC State publish research-backed
agronomic guidance. So advice should be either (a) a cited extension
finding conditioned on the field's computed stage/stress state, or (b) a
direct reading of the model's SHAP output (`api/routers/explain.py` already
computes this) — "your prediction is down mostly because July soil moisture
was well below your county's normal." Anything else is liability dressed as
a feature: farmers make five- and six-figure decisions on this, and a
fabricated recommendation is worse than no recommendation.

**Dependency chain this creates:** planting date (4b) → GDD staging
(Layer 1) → stage-aware stress features (Layer 2) → grounded advice
(Layer 3). That makes 4b's "low-effort tier" the *unlock* for the whole
agronomic direction, not the minor convenience it looked like when Phase 4
was first written.

### BUILT (2026-09): Layer 3 shipped for exactly the checkpoints Layer 2 measured

`src/field_advice.py` + `POST /fields/advice`, deliberately separate from
`/fields/predict` (same reasoning as Layer 1's `/fields/stage`): the SHAP
half needs a successful yield prediction, but the sourced-note half is keyed
off growth stage alone, so a small field the yield path correctly refuses can
still get a sourced note.

- **SHAP half**: reuses the exact feature row and model `predict_field.py`
  would use for this field (`predict_field.build_field_prediction_row()`,
  split out of `predict_field()` for this reuse rather than re-deriving the
  anomaly/trend/state-dummy steps a second time). The humanize/SHAP code
  itself moved out of `api/routers/explain.py` into `src/explain_utils.py`
  so the county and field explanations share one implementation instead of
  two copies that can drift.
- **Sourced-note half** (`src/advice_sources.py`): two citations, both
  paraphrased from real ISU Extension publications (corn pollination
  heat/drought sensitivity; soybean pod-set-through-seed-fill drought
  sensitivity), each gated on the field's own computed stage AND its own
  measured stress metrics actually being elevated -- not fired from stage
  alone. **Deliberately scoped to exactly the two (crop, checkpoint) pairs
  Layer 2 shipped stress features for** (`corn`/`early_season`,
  `soybeans`/`pre_harvest`, see `build_dataset.NEEDS_STRESS`): every other
  crop/checkpoint has no measured stress to condition on, so the honest
  answer there is no note, not a hedged one. `edd_29c > 0` is not an
  arbitrary cutoff (Schlenker & Roberts (2009) define that metric as
  degree-days above the point their yield-response curve turns negative);
  `dry_days >= 15` in a period IS a stated judgment call, same as the
  pixel-fraction cutoffs in the coverage-tier work above.
- Verified end to end: unit-tested `matching_notes()` against synthetic
  stress rows (fires only on the right crop + stage + elevated stress
  combination, confirmed silent otherwise), then live via `POST
  /fields/advice` against the real `kjkj` field (109.7ac corn, R3/milk stage)
  in the browser -- real SHAP contributions rendered under a real 192.4
  bu/acre prediction, no sourced note (correct: corn/pre_harvest isn't a
  NEEDS_STRESS checkpoint). `/predictions/explain` (county) re-verified
  unchanged after the explain_utils.py extraction.
- Built on a separate branch (`layer3-advice`) and verified only against a
  local dev server; not deployed to Modal or Vercel, so the public app is
  unaffected until a deploy is explicitly requested.

### Future (deferred, not in focus): the field calendar

The natural product form of Layers 1-3: a per-field calendar marking when
the operationally important windows arrive for *this* field at *this*
location — planting window, key growth stages, scouting windows, harvest
readiness. It is deliberately parked until the agronomic layers exist,
because it is only worth building on top of them.

The design point that separates this from a generic almanac: the dates
must be **derived, not hardcoded**. A static "plant corn in late April in
Iowa" table is something a farmer already knows and doesn't need an app
for. Projecting forward from *this field's* GDD accumulation against
climate normals — "at your accumulated heat units, this field reaches
pollination in roughly 9-14 days" — is genuinely field-specific and falls
straight out of Layer 1's staging. Same data, no new sources.

**Pesticide/spray timing carries real constraints and should be treated
differently from the rest.** Two reasons, both worth respecting rather
than designing around:
- *Agronomic*: integrated pest management is threshold-based — you scout,
  find pressure above a documented threshold, and then treat. Pest
  development itself is degree-day modelable (extension services publish
  per-pest models), so the honest output is **"conditions favor scouting
  for X now,"** never "spray now." A calendar that prompts calendar-based
  spraying is teaching a practice that IPM exists to prevent.
- *Regulatory/liability*: pesticide application is label-law regulated,
  with restricted-use products and applicator licensing. The app should
  surface timing and cite the extension source, and must not read as
  instructing an application.

Same sourcing rule as Layer 3 applies throughout: cite the extension
model, or don't make the claim.

**On-demand vs. precomputed, and where this lives in Supabase.** Field
predictions stay on-demand (`POST /fields/predict`, run when the farmer
clicks "Predict my field"), not a scheduled batch job like the public
county dashboard's Modal cron. A farmer has a handful of fields they check
occasionally; precomputing for every farmer's every field on a schedule
burns Earth Engine quota on fields nobody's looking at today. Sentinel-2's
extra cloud-masking compute makes each request somewhat slower (still
single-digit-to-tens of seconds, all server-side on Earth Engine — nothing
runs locally), which isn't a reason to precompute; if latency ever becomes
a real UX problem the fix is a job queue + notification, not a nightly batch.

This is not "very data heavy" in the way that phrase usually implies.
Earth Engine hosts the actual satellite imagery — this pipeline (Phase 2/3
and Sentinel-2 in 4a alike) never downloads pixels or rasters, only ever
pulls back a handful of aggregate numbers (`reduceRegion` results) per
field per request, the exact pattern already in production. What DOES need
a home in Supabase — all small structured rows, no file/blob storage
required:
- Farmer-submitted crop/planting-date/yield-history (4b) — new columns on
  `fields` plus a new `field_yield_history` table, RLS-scoped like the rest
  of Phase 1's schema (`src/supabase_farm_schema.sql`).
- The static soil/terrain cache Phase 2 already writes to
  `data/processed/field_static_cache/<field_id>.json` on local disk — move
  this into a small Supabase table instead. Local-filesystem caching
  doesn't survive a redeploy or multiple server instances once this API is
  actually hosted somewhere (still local-dev only, see Phase 6 below), so
  this was already going to need to move; Phase 4 is a reasonable time to
  do it since 4a touches the same fetch path anyway.
- Optionally, a `field_predictions` history table so a farmer can see how
  their field's prediction moved across a season instead of just their
  latest click — a nice product win, not required for 4a/4b themselves.

### Re-evaluated sequencing (2026-09, after 4a's validation)

The original Phase 4 order assumed 4a would finish cleanly and 4b was a
nice-to-have. The validation inverted that. Revised priority:

1. **4b's low-effort tier first — confirmed crop + planting date.** It was
   scoped as a convenience; it is actually the unlock for the entire
   agronomy direction above (no planting date → no GDD staging → no
   stage-aware features → no grounded advice). It also independently fixes
   the crop-guessing failure hit in live testing, where the app had to try
   corn, then soybeans, blind — on a field that turned out to be half
   alfalfa and grew neither in the amount MODIS claimed. Cheap, no model
   risk, unblocks the most valuable work.
2. **Decide Path A vs Path B for Sentinel-2** — a deliberate call, not a
   default. Path B is days; Path A is a retraining project. Worth deciding
   with the "is mid-season MODIS NDVI even informative?" check in hand,
   since if those features are near-dead in the current model, Path A's
   value rises sharply.
3. **Agronomic Layers 1-2** (GDD staging, stress features), which need (1).
   This is the largest expected accuracy gain of anything currently on the
   roadmap, and unlike Sentinel-2 it does not depend on resolving a sensor
   calibration problem.
4. **Layer 3 advice**, which needs (3) and should ship with citations.
5. Then Phase 5/6 below (delivery, hardening) as originally written.

Deliberately *not* doing yet: farmer yield history (4b's high-effort tier).
It remains the only path to true farmer-calibration, but it is worth
collecting only once there is enough product value to justify asking a
farmer for commercially sensitive numbers.

## Data flow (current, through Phase 3)

```
Historical (batch, src/fetch_*.py + build_dataset.py)
  USDA NASS / MODIS / PRISM / ERA5-Land / OpenLandMap / SRTM
    -> data/raw/ -> data/processed/model_table_<crop>_<checkpoint>.csv
    -> train_final_models.py -> models/gb_<crop>_<checkpoint>.joblib

Live, county-level (src/run_pipeline.py, scheduled)
  predict_live.py -> compare_crops.py -> Supabase (crop_predictions, crop_profitability)
    -> api/ (FastAPI, read-only) -> frontend/ (county map)

Farmer identity (Phase 1)
  frontend/ (farmer auth + field-drawing UI)
    -> Supabase (farmers, farms, fields -- RLS-scoped)

Live, field-level, on-demand (Phase 2 + 3, per click, not scheduled)
  frontend/ "Predict my field" -> POST /fields/predict
    -> src/predict_field.py -> src/fetch_field_features.py
      -> Earth Engine (MODIS/PRISM/ERA5-Land/SoilGrids/SRTM/CDL,
         reduceRegion over the field's own polygon)
      -> field_county() spatial join (TIGER/2018/Counties) for state/county
    -> models/gb_<crop>_<checkpoint>.joblib (same models as the county path)
    -> back to frontend (predicted yield + range + vs.-county comparison)
```

**Phase 4 addition (planned, not built)**: the field-level branch above
swaps its NDVI source from MODIS to Sentinel-2 (4a) and Supabase gains
`field_yield_history` + a `field_static_cache` table replacing the current
local-disk cache (4b) — see the Phase 4 writeup above for why. The
on-demand shape (arrow from frontend click straight through to Earth
Engine) doesn't change.

## Related docs

- `README.md` — pipeline details, model results, known limitations.
- `frontend/design-system/crop-yield-predictor/MASTER.md` — visual design
  system for the existing county-map product.
- `../ag-data-explorer/README.md` — the sibling public-data-site repo.
