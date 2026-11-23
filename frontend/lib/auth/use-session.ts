"use client";

import { useEffect, useState } from "react";

import { auth, type Session } from "@/lib/auth/client";

type SessionState = {
  session: Session | null;
  isLoading: boolean;
  error: string;
};

export function useSession(): SessionState {
  const [state, setState] = useState<SessionState>({ session: null, isLoading: true, error: "" });

  useEffect(() => {
    let cancelled = false;
    void auth.getSession().then(({ data }) => {
      if (!cancelled) setState({ session: data.session, isLoading: false, error: "" });
    });
    const { data } = auth.onAuthStateChange((_event, session) => {
      if (!cancelled) setState({ session, isLoading: false, error: "" });
    });
    return () => {
      cancelled = true;
      data.subscription.unsubscribe();
    };
  }, []);

  return state;
}
