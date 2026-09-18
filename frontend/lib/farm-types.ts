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

// Rows from src/supabase_farm_migration_calendar.sql -- the smart farm
// calendar's inputs. Due dates are NOT stored: they're derived on demand by
// POST /calendar/plan from these rows plus the cited knowledge files.
export interface Herd {
  id: number;
  farm_id: number;
  species: string;
  name: string;
  head_count: number | null;
  notes: string | null;
  created_at: string;
}

// An anchor date a schedule hangs off ("lambed", "breeding_start", ...).
// subject_id points at fields.id or herds.id depending on subject_type.
export interface FarmEvent {
  id: number;
  farm_id: number;
  subject_type: "field" | "herd";
  subject_id: number;
  kind: string;
  event_date: string;
  created_at: string;
}

export interface CalendarCompletion {
  id: number;
  farm_id: number;
  subject_type: "field" | "herd";
  subject_id: number;
  rule_id: string;
  occurrence_date: string;
  done_at: string;
  note: string | null;
}
