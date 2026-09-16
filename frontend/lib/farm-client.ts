import { supabase } from "./supabase-client";
import type { Farm, Field } from "./farm-types";
import type { GeoJSONPolygon } from "./geo";

// Every farmer gets exactly one auto-created farm in Phase 1's UI -- the
// `farms` table stays multi-farm-capable (see src/supabase_farm_schema.sql)
// for when that's actually needed, but nothing in this file assumes more
// than one exists yet.
export async function ensureDefaultFarm(farmerId: string, email?: string): Promise<Farm> {
  const { error: upsertError } = await supabase
    .from("farmers")
    .upsert({ id: farmerId, display_name: email ?? null }, { onConflict: "id" });
  if (upsertError) throw upsertError;

  const { data: existing, error: selectError } = await supabase
    .from("farms")
    .select("*")
    .eq("farmer_id", farmerId)
    .order("created_at", { ascending: true })
    .limit(1)
    .maybeSingle();
  if (selectError) throw selectError;
  if (existing) return existing as Farm;

  const { data: created, error: insertError } = await supabase
    .from("farms")
    .insert({ farmer_id: farmerId, name: "My farm" })
    .select()
    .single();
  if (insertError) throw insertError;
  return created as Farm;
}

export async function fetchFields(farmId: number): Promise<Field[]> {
  const { data, error } = await supabase
    .from("fields")
    .select("*")
    .eq("farm_id", farmId)
    .order("created_at", { ascending: false });
  if (error) throw error;
  return data as Field[];
}

export async function createField(params: {
  farmId: number;
  name: string;
  boundary: GeoJSONPolygon;
  acres: number;
  primaryCrop?: string;
  plantingDate?: string;
}): Promise<Field> {
  const { data, error } = await supabase
    .from("fields")
    .insert({
      farm_id: params.farmId,
      name: params.name,
      boundary: params.boundary,
      acres: params.acres,
      primary_crop: params.primaryCrop ?? null,
      planting_date: params.plantingDate || null,
    })
    .select()
    .single();
  if (error) throw error;
  return data as Field;
}

// Crop and planting date change every season on the same physical field, so
// these are editable after creation -- unlike the boundary, which doesn't
// move. Phase 4b (see ../../ARCHITECTURE.md).
export async function updateFieldSeason(
  fieldId: number,
  params: { primaryCrop?: string | null; plantingDate?: string | null }
): Promise<Field> {
  const patch: Record<string, string | null> = {};
  if (params.primaryCrop !== undefined) patch.primary_crop = params.primaryCrop || null;
  if (params.plantingDate !== undefined) patch.planting_date = params.plantingDate || null;

  const { data, error } = await supabase
    .from("fields")
    .update(patch)
    .eq("id", fieldId)
    .select()
    .single();
  if (error) throw error;
  return data as Field;
}

export async function deleteField(fieldId: number): Promise<void> {
  const { error } = await supabase.from("fields").delete().eq("id", fieldId);
  if (error) throw error;
}
