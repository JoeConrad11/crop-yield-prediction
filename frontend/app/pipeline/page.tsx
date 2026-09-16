"use client";

import {
  Calendar,
  Droplets,
  Flame,
  FlaskConical,
  Leaf,
  Mountain,
  Sprout,
} from "lucide-react";
import { useEffect, useState } from "react";

import { AppHeader } from "@/components/app-header";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Deployed Modal endpoint for the Assignment 4 pipeline API (see
// /assignment4/modal_serve.py in the repo). Hardcoded as the default so this
// page always talks to the live API even if the env var isn't set on
// Vercel -- an override is still supported for local testing against
// `uvicorn serve:app --reload`.
const API_URL =
  process.env.NEXT_PUBLIC_PIPELINE_API_URL ??
  "https://jconrad8--yield-anomaly-pipeline-api-fastapi-app.modal.run";

type InfoResponse = {
  metadata: {
    steps: string[];
    built_at: string;
    sklearn_version: string;
    n_train_rows: number;
    n_counties: number;
    source: string;
  };
  value_cols: string[];
  static_cols: string[];
  target: string;
};

type PredictResponse = {
  predicted_yield_bu_acre: number;
  known_county: boolean;
};

const DEFAULT_FORM = {
  state_fips: 19,
  county_fips: 169,
  year: 2024,
  ndvi_jun: 0.55,
  ndvi_jul: 0.78,
  precip_sum_jun: 110,
  precip_sum_jul: 95,
  tmean_jun: 21.5,
  tmean_jul: 24.0,
  edd_29c_jul: 15.0,
  dry_days_jul: 8,
  soil_organic_carbon: 25.0,
  soil_ph: 6.5,
  elevation_m: 320,
  slope_deg: 2.5,
};

type FormState = typeof DEFAULT_FORM;
type FieldKey = keyof FormState;

const FIELD_GROUPS: {
  title: string;
  icon: typeof Leaf;
  fields: { key: FieldKey; label: string; step?: string; unit?: string }[];
}[] = [
  {
    title: "Location & year",
    icon: Calendar,
    fields: [
      { key: "state_fips", label: "State FIPS" },
      { key: "county_fips", label: "County FIPS" },
      { key: "year", label: "Year" },
    ],
  },
  {
    title: "Vegetation (NDVI)",
    icon: Leaf,
    fields: [
      { key: "ndvi_jun", label: "June", step: "0.01" },
      { key: "ndvi_jul", label: "July", step: "0.01" },
    ],
  },
  {
    title: "Weather",
    icon: Droplets,
    fields: [
      { key: "precip_sum_jun", label: "Precip, June", unit: "mm" },
      { key: "precip_sum_jul", label: "Precip, July", unit: "mm" },
      { key: "tmean_jun", label: "Mean temp, June", unit: "C" },
      { key: "tmean_jul", label: "Mean temp, July", unit: "C" },
    ],
  },
  {
    title: "Heat & dry stress",
    icon: Flame,
    fields: [
      { key: "edd_29c_jul", label: "Extreme degree days >29C, July" },
      { key: "dry_days_jul", label: "Dry days, July" },
    ],
  },
  {
    title: "Soil & terrain",
    icon: Mountain,
    fields: [
      { key: "soil_organic_carbon", label: "Soil organic carbon" },
      { key: "soil_ph", label: "Soil pH", step: "0.1" },
      { key: "elevation_m", label: "Elevation", unit: "m" },
      { key: "slope_deg", label: "Slope", unit: "deg" },
    ],
  },
];

function InfoSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
      <div className="h-3 w-1/2 animate-pulse rounded bg-muted" />
      <div className="h-3 w-1/3 animate-pulse rounded bg-muted" />
    </div>
  );
}

export default function Assignment4Page() {
  const [info, setInfo] = useState<InfoResponse | null>(null);
  const [infoError, setInfoError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [result, setResult] = useState<PredictResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/info`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        return res.json();
      })
      .then(setInfo)
      .catch((err) => setInfoError(String(err)));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_URL}/predict`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(`${res.status}: ${body ? JSON.stringify(body.detail) : res.statusText}`);
      }
      setResult(await res.json());
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <AppHeader subtitle="Assignment 4 -- a fitted scikit-learn Pipeline, served live from Modal" />

      <main className="mx-auto w-full max-w-4xl flex-1 space-y-6 px-4 py-8 sm:px-6">
        <section className="rounded-xl border border-border bg-card p-6 shadow-sm transition-all duration-200 hover:shadow-md">
          <div className="flex items-start gap-3">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FlaskConical className="size-5" aria-hidden="true" />
            </div>
            <div>
              <h1 className="font-heading text-xl font-semibold text-card-foreground">
                County Yield Anomaly Pipeline
              </h1>
              <p className="mt-1 text-sm text-muted-foreground">
                A custom <code className="rounded bg-muted px-1 py-0.5 text-xs">CountyAnomalyTransformer</code>{" "}
                learns each county&apos;s multi-year baseline, then a{" "}
                <code className="rounded bg-muted px-1 py-0.5 text-xs">GradientBoostingRegressor</code> predicts
                corn yield from how far this year deviates from it.
              </p>
            </div>
          </div>

          <div className="mt-5 border-t border-border pt-4">
            {infoError && (
              <p className="text-sm text-destructive">Couldn&apos;t load pipeline info: {infoError}</p>
            )}
            {!info && !infoError && <InfoSkeleton />}
            {info && (
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
                <div>
                  <dt className="text-xs text-muted-foreground">Pipeline steps</dt>
                  <dd className="mt-0.5 flex flex-wrap gap-1">
                    {info.metadata.steps.map((step) => (
                      <span
                        key={step}
                        className="rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground"
                      >
                        {step}
                      </span>
                    ))}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">sklearn version</dt>
                  <dd className="mt-0.5 font-medium text-card-foreground">{info.metadata.sklearn_version}</dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Training rows</dt>
                  <dd className="mt-0.5 font-medium text-card-foreground">
                    {info.metadata.n_train_rows.toLocaleString()} ({info.metadata.n_counties} counties)
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-muted-foreground">Built at</dt>
                  <dd className="mt-0.5 font-medium text-card-foreground">
                    {new Date(info.metadata.built_at).toLocaleString()}
                  </dd>
                </div>
              </dl>
            )}
          </div>
        </section>

        <form onSubmit={handleSubmit} className="space-y-4">
          {FIELD_GROUPS.map(({ title, icon: Icon, fields }) => (
            <fieldset
              key={title}
              className="rounded-xl border border-border bg-card p-5 shadow-sm transition-all duration-200 hover:shadow-md"
            >
              <legend className="flex items-center gap-2 px-1 font-heading text-sm font-semibold text-card-foreground">
                <Icon className="size-4 text-primary" aria-hidden="true" />
                {title}
              </legend>
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                {fields.map(({ key, label, step, unit }) => (
                  <label key={key} className="flex flex-col gap-1 text-xs">
                    <span className="text-muted-foreground">
                      {label}
                      {unit ? ` (${unit})` : ""}
                    </span>
                    <input
                      type="number"
                      step={step ?? "any"}
                      value={form[key]}
                      onChange={(e) => setForm((f) => ({ ...f, [key]: Number(e.target.value) }))}
                      className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground transition-colors duration-200 focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/20"
                    />
                  </label>
                ))}
              </div>
            </fieldset>
          ))}

          <div className="flex justify-end">
            <Button type="submit" disabled={loading} size="lg" className="px-6">
              {loading ? "Predicting..." : "Predict yield"}
            </Button>
          </div>
        </form>

        {error && (
          <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {result && (
          <div className="flex items-center gap-4 rounded-xl border border-border bg-card p-6 shadow-sm transition-all duration-200 hover:shadow-md">
            <div className="flex size-12 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
              <Sprout className="size-6" aria-hidden="true" />
            </div>
            <div>
              <p className="font-heading text-2xl font-semibold text-card-foreground">
                {result.predicted_yield_bu_acre.toFixed(1)}{" "}
                <span className="text-base font-normal text-muted-foreground">bu/acre</span>
              </p>
              <p
                className={cn(
                  "text-sm",
                  result.known_county ? "text-muted-foreground" : "text-accent"
                )}
              >
                {result.known_county
                  ? "This county had its own fitted anomaly baseline."
                  : "Unknown county at fit time -- fell back to the global anomaly baseline."}
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
