"use client";

import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import { createSupabaseBrowserClient } from "@/lib/supabase/client";

type SessionState = {
  session: Session | null;
  isLoading: boolean;
  error: string;
};

export function useSession(): SessionState {
  const [state, setState] = useState<SessionState>({
    session: null,
    isLoading: true,
    error: "",
  });

  useEffect(() => {
    let unsubscribe: (() => void) | undefined;
    let cancelled = false;

    void (async () => {
      try {
        const supabase = createSupabaseBrowserClient();
        const { data, error } = await supabase.auth.getSession();
        if (error) setState((current) => ({ ...current, error: error.message }));
        if (!cancelled) setState((current) => ({ ...current, session: data.session }));
        const { data: subscription } = supabase.auth.onAuthStateChange((_event, nextSession) => {
          if (!cancelled) setState((current) => ({ ...current, session: nextSession }));
        });
        unsubscribe = () => subscription.subscription.unsubscribe();
      } catch (error) {
        if (!cancelled) {
          setState((current) => ({
            ...current,
            error: error instanceof Error ? error.message : "No fue posible configurar Supabase.",
          }));
        }
      } finally {
        if (!cancelled) setState((current) => ({ ...current, isLoading: false }));
      }
    })();

    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, []);

  return state;
}