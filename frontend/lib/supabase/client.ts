import { createClient } from "@supabase/supabase-js";

let _client: ReturnType<typeof createClient> | undefined;

export function createSupabaseBrowserClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    throw new Error("Faltan NEXT_PUBLIC_SUPABASE_URL o NEXT_PUBLIC_SUPABASE_ANON_KEY.");
  }
  if (!_client) {
    _client = createClient(url, anonKey);
  }
  return _client;
}
