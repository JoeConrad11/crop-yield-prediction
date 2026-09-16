// Rows from Supabase's farmers/farms/fields tables (src/supabase_farm_schema.sql)
// -- private, RLS-scoped farmer data, not pipeline output. Separate from
// types.ts, which mirrors api/models.py (the public FastAPI layer).
import type { GeoJSONPolygon } from "./geo";

export interface Farm {
  id: number;
  farmer_id: string;
  name: string;
  created_at: string;
}

export interface Field {
  id: number;
  farm_id: number;
  name: string;
  boundary: GeoJSONPolygon;
  acres: number | null;
  // Farmer-reported and authoritative -- preferred over the CDL-derived
  // guess, which is published a year late and is therefore wrong on any
  // field that rotates (see src/supabase_farm_migration_planting.sql).
  primary_crop: string | null;
  // Origin for Growing Degree Day accumulation -> growth staging. ISO date
  // string (YYYY-MM-DD); Postgres `date`, so no timezone component.
  planting_date: string | null;
  created_at: string;
}
