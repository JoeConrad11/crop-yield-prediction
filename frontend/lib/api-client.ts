import type {
  BacktestPoint,
  CountyComparison,
  CountyGeoJSON,
  CropMeta,
  PredictionExplanation,
  PredictionOut,
  StateGeoJSON,
  YieldHistoryPoint,
} from "./types";

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
