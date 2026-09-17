// Mirrors api/models.py -- not a separate source of truth. Crop identity is
// always a free-form string (whatever's in src/config.py CROPS), never a
// union of literal crop names, so a new crop needs no type change here.

export interface CropMeta {
  id: string;
  display_name: string;
  nass_commodity: string;
}

export interface PredictionOut {
  crop: string;
  year: number;
  state_fips: string;
  county_fips: string;
  county_name: string;
  checkpoint: string;
  predicted_yield_bu_acre: number;
  predicted_yield_low: number | null;
  predicted_yield_high: number | null;
  confidence_mae: number | null;
  coverage_tier: string | null;
  crop_pixel_coverage: number | null;
  historical_avg_yield: number | null;
  delta_vs_historical: number | null;
  pct_vs_historical: number | null;
}

export interface FieldPrediction extends PredictionOut {
  field_id: string | null;
  // How much crop area actually backed the reading vs. how big the field
  // is -- `coverage_tier` for a field is derived from these, not from the
  // sensor-specific pixel count (see src/fetch_field_features.py).
  crop_observed_acres: number | null;
  field_acres: number | null;
}

// Agronomy Layer 1 (see ../../ARCHITECTURE.md). Available for ANY field
// size -- it comes from 4km temperature data, so unlike the yield
// prediction it has no small-field resolution limit.
export interface GrowthStageMarker {
  code: string;
  description: string;
  gdd_threshold: number;
}

export interface FieldGrowthStage {
  crop: string;
  planting_date: string;
  as_of: string;
  days_since_planting: number;
  accumulated_gdd: number;
  stage: GrowthStageMarker | null; // null before emergence
  next_stage: GrowthStageMarker | null; // null past the last modelled stage
  next_stage_gdd_away: number | null;
  confidence: string;
  caveat: string;
}

// Same-growth-stage year-over-year comparison -- the small-farm monitoring
// product. Works at any field size (see ../../ARCHITECTURE.md).
export interface FieldBenchmarkYear {
  year: number;
  equivalent_date: string | null; // null if that season never got this warm
  ndvi: number | null;
  pixels?: number;
  window_days?: number;
  note?: string;
}

export interface FieldStageBenchmark {
  crop: string;
  planting_date: string;
  as_of: string;
  stage: GrowthStageMarker | null;
  accumulated_gdd: number;
  current_ndvi: number | null;
  current_pixels: number;
  current_window_days: number;
  history: FieldBenchmarkYear[];
  history_mean_ndvi?: number;
  history_sd_ndvi?: number;
  pct_vs_history?: number;
  sd_from_history?: number | null;
  comparison_basis: string;
  planting_assumption: string;
  message?: string;
}

export interface CropProfitability {
  yield_bu_acre: number | null;
  price_per_bu: number | null;
  cost_per_acre: number | null;
  revenue_per_acre: number | null;
  profit_per_acre: number | null;
}

export interface CountyComparison {
  state_fips: string;
  county_fips: string;
  county_name: string;
  state_alpha: string;
  crops: Record<string, CropProfitability>;
  best_crop: string | null;
  margin_dollars: number | null;
}

export interface YieldHistoryPoint {
  year: number;
  yield_bu_acre: number;
}

export interface BacktestPoint {
  year: number;
  actual_yield_bu_acre: number;
  predicted_yield_bu_acre: number;
}

export interface ExplainContribution {
  feature: string;
  label: string;
  value: number;
  shap_value_bu_acre: number;
}

export interface PredictionExplanation {
  predicted_yield_bu_acre: number;
  base_value_bu_acre: number;
  trend_contribution_bu_acre: number;
  top_contributions: ExplainContribution[];
  other_contribution_bu_acre: number;
  other_feature_count: number;
}

// Layer 3 (see ../../ARCHITECTURE.md, "Layer 3 -- Advice, sourced not
// invented"). shap_explanation is null when the yield path can't produce a
// number for this field/season (see shap_unavailable_reason); sourced_notes
// is an empty array whenever nothing measured warrants a citation, which is
// the common case -- both are honest "nothing to say," not errors.
export interface FieldAdviceExplanation {
  base_value_bu_acre: number;
  trend_contribution_bu_acre: number;
  top_contributions: ExplainContribution[];
  other_contribution_bu_acre: number;
  other_feature_count: number;
}

export interface FieldAdviceNote {
  id: string;
  source_name: string;
  source_url: string;
  text: string;
}

export interface FieldAdvice {
  crop: string;
  stage: GrowthStageMarker | null;
  shap_explanation: FieldAdviceExplanation | null;
  shap_unavailable_reason: string | null;
  sourced_notes: FieldAdviceNote[];
}

export interface CountyGeoJSON {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    properties: { state_fips: string; county_fips: string; county_name: string };
    geometry: { type: string; coordinates: unknown };
  }>;
}

// Full-US backdrop -- context only, not project data (see api/scripts/build_states_geojson.py).
export interface StateGeoJSON {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    properties: { state_fips: string; state_name: string };
    geometry: { type: string; coordinates: unknown };
  }>;
}
