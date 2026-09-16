import { createClient } from "@supabase/supabase-js";

// Talks directly to Supabase (auth + the farmers/farms/fields tables from
// src/supabase_farm_schema.sql), unlike api-client.ts which goes through
// the FastAPI service. Farmer data is private/RLS-scoped, not pipeline
// output -- see ARCHITECTURE.md's "keep concerns separate" note. The anon
// key is safe in the browser; RLS is what actually restricts access.
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    "Missing NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY -- see frontend/.env.local.example"
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
