import type {
  BacktestPoint,
  CountyComparison,
  CountyGeoJSON,
  CropMeta,
  FieldGrowthStage,
  FieldStageBenchmark,
  FieldPrediction,
  PredictionExplanation,
  PredictionOut,
  StateGeoJSON,
  YieldHistoryPoint,
} from "./types";
import type { GeoJSONPolygon } from "./geo";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export function fetchCrops(): Promise<CropMeta[]> {
  return getJSON<CropMeta[]>("/crops");
}

export function fetchLatestPredictions(params: { crop?: string; state?: string; county?: string } = {}): Promise<PredictionOut[]> {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return getJSON<PredictionOut[]>(`/predictions/latest${qs ? `?${qs}` : ""}`);
}

export function fetchComparisons(
  params: { as_of?: string; state?: string; county?: string } = {}
): Promise<CountyComparison[]> {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return getJSON<CountyComparison[]>(`/comparisons${qs ? `?${qs}` : ""}`);
}

export function fetchCountyGeoJSON(state?: string): Promise<CountyGeoJSON> {
  const qs = state ? `?state=${state}` : "";
  return getJSON<CountyGeoJSON>(`/geo/counties${qs}`);
}

export function fetchYieldHistory(params: { crop: string; state: string; county: string }): Promise<YieldHistoryPoint[]> {
  const qs = new URLSearchParams(params).toString();
  return getJSON<YieldHistoryPoint[]>(`/predictions/history?${qs}`);
}

export function fetchStatesGeoJSON(): Promise<StateGeoJSON> {
  return getJSON<StateGeoJSON>("/geo/states");
}

export function fetchBacktestPredictions(
  params: { crop: string; state: string; county: string; checkpoint?: string }
): Promise<BacktestPoint[]> {
  const qs = new URLSearchParams(params).toString();
  return getJSON<BacktestPoint[]>(`/predictions/backtest?${qs}`);
}

export function fetchExplanation(
  params: { crop: string; state: string; county: string; checkpoint?: string }
): Promise<PredictionExplanation> {
  const qs = new URLSearchParams(params).toString();
  return getJSON<PredictionExplanation>(`/predictions/explain?${qs}`);
}

// Codes the field-prediction endpoint returns for a well-formed request it
// honestly can't answer (see api/routers/field_predict.py). These are
// LIMITATIONS, not failures -- `unreliable_coverage` in particular is the
// expected outcome for a small field on MODIS imagery -- so the UI presents
// them differently from a genuine error.
export type FieldPredictionLimitation =
  | "unreliable_coverage"
  | "insufficient_coverage"
  | "season_not_started"
  | "unsupported_region"
  // growth-stage limitations (POST /fields/stage)
  | "no_planting_date"
  | "no_stage_model"
  | "planting_in_future"
  | "no_temperature_data";

export class FieldPredictionError extends Error {
  constructor(message: string, readonly code?: FieldPredictionLimitation) {
    super(message);
    this.name = "FieldPredictionError";
  }

  // True when the pipeline worked correctly and the honest answer is "not
  // for this field, this season" -- not when something actually broke.
  get isLimitation(): boolean {
    return this.code !== undefined;
  }
}

// Phase 3 (see ../../ARCHITECTURE.md): the only POST this API layer makes --
// everything else reads pre-computed Supabase rows, this one runs live Earth
// Engine + model inference for a single farmer-drawn field, so it takes a
// few seconds and can come back with a 422 carrying one of the limitation
// codes above rather than a result.
export async function predictField(params: {
  boundary: GeoJSONPolygon;
  crop: string;
  fieldId?: string;
}): Promise<FieldPrediction> {
  const res = await fetch(`${API_BASE}/fields/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ boundary: params.boundary, crop: params.crop, field_id: params.fieldId ?? null }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    if (detail && typeof detail === "object" && typeof detail.message === "string") {
      throw new FieldPredictionError(detail.message, detail.code);
    }
    throw new FieldPredictionError(
      typeof detail === "string" ? detail : `Prediction failed: ${res.status} ${res.statusText}`
    );
  }
  return res.json() as Promise<FieldPrediction>;
}

// Growth stage from the farmer's planting date + accumulated heat. Kept
// separate from predictField on purpose: this works at ANY field size,
// including the small fields the yield endpoint correctly refuses, so it
// must never be gated behind a prediction succeeding.
export async function fetchFieldStage(params: {
  boundary: GeoJSONPolygon;
  crop: string;
  plantingDate?: string | null;
  fieldId?: string;
}): Promise<FieldGrowthStage> {
  const res = await fetch(`${API_BASE}/fields/stage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      boundary: params.boundary,
      crop: params.crop,
      planting_date: params.plantingDate ?? null,
      field_id: params.fieldId ?? null,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    if (detail && typeof detail === "object" && typeof detail.message === "string") {
      throw new FieldPredictionError(detail.message, detail.code);
    }
    throw new FieldPredictionError(
      typeof detail === "string" ? detail : `Growth stage failed: ${res.status} ${res.statusText}`
    );
  }
  return res.json() as Promise<FieldGrowthStage>;
}

// The small-farm monitoring product: this field's canopy now vs. the same
// field at the same GROWTH STAGE in prior seasons. Slower than the other
// calls (several years of daily temperature plus a Sentinel-2 composite per
// season), so callers should expect ~10-30s and show progress.
export async function fetchFieldBenchmark(params: {
  boundary: GeoJSONPolygon;
  crop: string;
  plantingDate?: string | null;
  fieldId?: string;
}): Promise<FieldStageBenchmark> {
  const res = await fetch(`${API_BASE}/fields/benchmark`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      boundary: params.boundary,
      crop: params.crop,
      planting_date: params.plantingDate ?? null,
      field_id: params.fieldId ?? null,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    if (detail && typeof detail === "object" && typeof detail.message === "string") {
      throw new FieldPredictionError(detail.message, detail.code);
    }
    throw new FieldPredictionError(
      typeof detail === "string" ? detail : `Benchmark failed: ${res.status} ${res.statusText}`
    );
  }
  return res.json() as Promise<FieldStageBenchmark>;
}
