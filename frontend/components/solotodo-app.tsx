"use client";

import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import { AuthPanel } from "@/components/auth/auth-panel";
import { ChatInterface } from "@/components/chat/chat-interface";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";

export function SoloTodoApp() {
  const [session, setSession] = useState<Session | null>(null);
  const [isLoadingSession, setIsLoadingSession] = useState(true);
  const [configurationError, setConfigurationError] = useState("");

  useEffect(() => {
    let unsubscribe: (() => void) | undefined;

    async function loadSession() {
      try {
        const supabase = createSupabaseBrowserClient();
        const { data, error } = await supabase.auth.getSession();
        if (error) setConfigurationError(error.message);
        setSession(data.session);
        setIsLoadingSession(false);
        const { data: subscription } = supabase.auth.onAuthStateChange((_event, nextSession) => setSession(nextSession));
        unsubscribe = () => subscription.subscription.unsubscribe();
      } catch (error) {
        setConfigurationError(error instanceof Error ? error.message : "No fue posible configurar Supabase.");
        setIsLoadingSession(false);
      }
    }

    void loadSession();
    return () => unsubscribe?.();
  }, []);

  async function logout() {
    try {
      const { error } = await createSupabaseBrowserClient().auth.signOut();
      if (error) setConfigurationError(error.message);
    } catch (error) {
      setConfigurationError(error instanceof Error ? error.message : "No fue posible cerrar sesión.");
    }
  }

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3"><span className="flex size-9 items-center justify-center rounded-xl bg-indigo-600 font-bold text-white" aria-hidden="true">S</span><span className="font-semibold tracking-tight text-slate-950">SoloTodo <span className="text-indigo-600">AI</span></span></div>
          {session ? <div className="flex items-center gap-3"><span className="hidden text-sm text-slate-500 sm:inline">{session.user.email}</span><button className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50" onClick={() => void logout()}>Cerrar sesión</button></div> : <span className="text-sm font-medium text-slate-500">Sesión requerida</span>}
        </div>
      </header>
      <div className="mx-auto max-w-5xl px-5 py-8 sm:px-8 sm:py-12">
        {configurationError && <p className="mb-5 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700" role="alert">{configurationError}</p>}
        {isLoadingSession ? <p className="py-20 text-center text-sm text-slate-500">Comprobando sesión…</p> : session ? <ChatInterface accessToken={session.access_token} /> : <AuthPanel onAuthenticated={setSession} />}
      </div>
    </main>
  );
}
