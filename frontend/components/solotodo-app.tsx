"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type { Session } from "@supabase/supabase-js";

import { ChatInterface } from "@/components/chat/chat-interface";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";

export function SoloTodoApp() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [session, setSession] = useState<Session | null>(null);
  const [isLoadingSession, setIsLoadingSession] = useState(true);
  const [configurationError, setConfigurationError] = useState("");

  const productParam = searchParams.get("product");
  const productId = productParam && /^\d+$/.test(productParam) ? Number(productParam) : null;
  const productName = searchParams.get("name");

  useEffect(() => {
    if (isLoadingSession || session) return;
    const params = new URLSearchParams();
    if (productId !== null) params.set("product", String(productId));
    if (productName) params.set("name", productName);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    router.replace(`/login${suffix}`);
  }, [isLoadingSession, session, productId, productName, router]);

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

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
      {configurationError && (
        <p className="mb-5 rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive" role="alert">
          {configurationError}
        </p>
      )}
      {isLoadingSession ? (
        <p className="py-20 text-center text-sm text-muted-foreground">Comprobando sesión…</p>
      ) : session ? (
        <ChatInterface accessToken={session.access_token} productId={productId} productName={productName} />
      ) : (
        <p className="py-20 text-center text-sm text-muted-foreground">Redirigiendo al inicio de sesión…</p>
      )}
    </div>
  );
}