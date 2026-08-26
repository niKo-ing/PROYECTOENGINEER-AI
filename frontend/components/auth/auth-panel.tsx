"use client";

import { FormEvent, useState } from "react";
import type { Session } from "@supabase/supabase-js";

import { createSupabaseBrowserClient } from "@/lib/supabase/client";

type AuthPanelProps = {
  onAuthenticated: (session: Session) => void;
};

export function AuthPanel({ onAuthenticated }: AuthPanelProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState<"login" | "register" | null>(null);

  async function authenticate(mode: "login" | "register") {
    setPending(mode);
    setMessage("");
    try {
      const supabase = createSupabaseBrowserClient();
      const result = mode === "login"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password });
      if (result.error) throw result.error;
      if (result.data.session) {
        onAuthenticated(result.data.session);
        return;
      }
      setMessage("Revisa tu correo para confirmar el registro y luego inicia sesión.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "No fue posible autenticar.");
    } finally {
      setPending(null);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void authenticate("login");
  }

  return (
    <section className="mx-auto w-full max-w-md rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <p className="text-sm font-medium text-indigo-600">Tu sesión protege tus preferencias</p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">Ingresa para conversar</h1>
      <p className="mt-2 text-sm leading-6 text-slate-600">Usaremos tu sesión de SoloTodo para consultar el asistente de forma segura.</p>
      <form className="mt-6 space-y-4" onSubmit={submit}>
        <label className="block text-sm font-medium text-slate-700">
          Correo
          <input className="mt-1.5 w-full rounded-xl border border-slate-300 px-3 py-2.5 outline-none transition focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          Contraseña
          <input className="mt-1.5 w-full rounded-xl border border-slate-300 px-3 py-2.5 outline-none transition focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={6} />
        </label>
        <button className="w-full rounded-xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60" type="submit" disabled={pending !== null}>
          {pending === "login" ? "Ingresando…" : "Ingresar"}
        </button>
        <button className="w-full rounded-xl border border-slate-300 px-4 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60" type="button" disabled={pending !== null} onClick={() => void authenticate("register")}>
          {pending === "register" ? "Creando cuenta…" : "Crear cuenta"}
        </button>
      </form>
      {message && <p className="mt-4 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800" role="status">{message}</p>}
    </section>
  );
}
