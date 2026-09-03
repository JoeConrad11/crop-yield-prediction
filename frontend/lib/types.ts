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
