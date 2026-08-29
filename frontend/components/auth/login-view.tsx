"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getFriendlyAuthMessage } from "@/lib/auth/auth-errors";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";

const loginSchema = z.object({
  email: z
    .string()
    .min(1, { error: "Ingresá tu correo." })
    .pipe(z.email({ error: "El correo no es válido." })),
  password: z.string().min(1, { error: "Ingresá tu contraseña." }),
});

type LoginValues = z.infer<typeof loginSchema>;

export function LoginView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  const { register, handleSubmit, formState } = form;

  async function onSubmit(values: LoginValues) {
    setSubmitting(true);
    setSubmitError("");
    try {
      const { data, error } = await createSupabaseBrowserClient().auth.signInWithPassword(values);
      if (error) {
        setSubmitError(getFriendlyAuthMessage(error, "login"));
        return;
      }
      if (!data.session) {
        setSubmitError("No pudimos iniciar sesión. Intentá de nuevo.");
        return;
      }
      router.push(chatTarget(searchParams));
      router.refresh();
    } catch (error) {
      setSubmitError(getFriendlyAuthMessage(error, "login"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell
      title="Iniciá sesión para conversar"
      description="Usaremos tu sesión de SoloTodo para consultar el asistente de forma segura."
    >
      <form className="mt-6 space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <div className="space-y-2">
          <Label htmlFor="login-email">Correo</Label>
          <Input
            id="login-email"
            type="email"
            autoComplete="email"
            placeholder="tucorreo@ejemplo.com"
            aria-invalid={Boolean(formState.errors.email)}
            {...register("email")}
          />
          {formState.errors.email ? (
            <p className="text-sm text-destructive" role="alert">
              {formState.errors.email.message}
            </p>
          ) : null}
        </div>
        <div className="space-y-2">
          <Label htmlFor="login-password">Contraseña</Label>
          <Input
            id="login-password"
            type="password"
            autoComplete="current-password"
            aria-invalid={Boolean(formState.errors.password)}
            {...register("password")}
          />
          {formState.errors.password ? (
            <p className="text-sm text-destructive" role="alert">
              {formState.errors.password.message}
            </p>
          ) : null}
        </div>
        {submitError && (
          <p className="rounded-xl bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
            {submitError}
          </p>
        )}
        <Button type="submit" size="lg" className="w-full" disabled={submitting}>
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Ingresando…
            </>
          ) : (
            "Iniciar sesión"
          )}
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-muted-foreground">
        ¿No tenés una cuenta?{" "}
        <Link href="/register" className="font-medium text-primary hover:underline">
          Crear cuenta
        </Link>
      </p>
    </AuthShell>
  );
}

export function chatTarget(searchParams: URLSearchParams): string {
  const product = searchParams.get("product");
  const name = searchParams.get("name");
  const params = new URLSearchParams();
  if (product) params.set("product", product);
  if (name) params.set("name", name);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/chat${suffix}`;
}