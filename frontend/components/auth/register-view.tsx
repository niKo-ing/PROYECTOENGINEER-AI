"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { chatTarget } from "@/components/auth/login-view";
import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getFriendlyAuthMessage } from "@/lib/auth/auth-errors";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";

const registerSchema = z
  .object({
    name: z
      .string()
      .trim()
      .min(2, { error: "Ingresá tu nombre." })
      .max(80, { error: "El nombre es demasiado largo." }),
    email: z
      .string()
      .min(1, { error: "Ingresá tu correo." })
      .pipe(z.email({ error: "El correo no es válido." })),
    password: z.string().min(6, { error: "La contraseña debe tener al menos 6 caracteres." }),
    confirmPassword: z.string().min(6, { error: "Confirmá tu contraseña." }),
  })
  .superRefine((values, ctx) => {
    if (values.password !== values.confirmPassword) {
      ctx.addIssue({
        code: "custom",
        message: "Las contraseñas no coinciden.",
        path: ["confirmPassword"],
      });
    }
  });

type RegisterValues = z.infer<typeof registerSchema>;

export function RegisterView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [created, setCreated] = useState(false);

  const form = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { name: "", email: "", password: "", confirmPassword: "" },
  });
  const { register, handleSubmit, formState } = form;

  async function onSubmit(values: RegisterValues) {
    setSubmitting(true);
    setSubmitError("");
    try {
      const { data, error } = await createSupabaseBrowserClient().auth.signUp({
        email: values.email,
        password: values.password,
        options: { data: { name: values.name } },
      });
      if (error) {
        setSubmitError(getFriendlyAuthMessage(error, "register"));
        return;
      }
      if (data.session) {
        router.push(chatTarget(searchParams));
        router.refresh();
        return;
      }
      setCreated(true);
    } catch (error) {
      setSubmitError(getFriendlyAuthMessage(error, "register"));
    } finally {
      setSubmitting(false);
    }
  }

  if (created) {
    return (
      <AuthShell
        title="Cuenta creada"
        description="Revisá tu correo para confirmar tu cuenta y luego iniciá sesión."
      >
        <div className="mt-6 space-y-4">
          <p className="rounded-xl bg-primary/10 px-3 py-2 text-sm text-primary" role="status">
            Cuenta creada. Revisá tu correo para confirmar tu cuenta.
          </p>
          <Button
            type="button"
            variant="outline"
            size="lg"
            className="w-full"
            onClick={() => router.push("/login")}
          >
            Ir a iniciar sesión
          </Button>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Creá tu cuenta"
      description="Guardá tus preferencias y hablá con el asistente de SoloTodo."
    >
      <form className="mt-6 space-y-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        <div className="space-y-2">
          <Label htmlFor="register-name">Nombre</Label>
          <Input
            id="register-name"
            type="text"
            autoComplete="name"
            placeholder="Tu nombre"
            aria-invalid={Boolean(formState.errors.name)}
            {...register("name")}
          />
          {formState.errors.name ? (
            <p className="text-sm text-destructive" role="alert">
              {formState.errors.name.message}
            </p>
          ) : null}
        </div>
        <div className="space-y-2">
          <Label htmlFor="register-email">Correo</Label>
          <Input
            id="register-email"
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
          <Label htmlFor="register-password">Contraseña</Label>
          <Input
            id="register-password"
            type="password"
            autoComplete="new-password"
            aria-invalid={Boolean(formState.errors.password)}
            {...register("password")}
          />
          {formState.errors.password ? (
            <p className="text-sm text-destructive" role="alert">
              {formState.errors.password.message}
            </p>
          ) : null}
        </div>
        <div className="space-y-2">
          <Label htmlFor="register-confirm-password">Confirmar contraseña</Label>
          <Input
            id="register-confirm-password"
            type="password"
            autoComplete="new-password"
            aria-invalid={Boolean(formState.errors.confirmPassword)}
            {...register("confirmPassword")}
          />
          {formState.errors.confirmPassword ? (
            <p className="text-sm text-destructive" role="alert">
              {formState.errors.confirmPassword.message}
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
              Creando cuenta…
            </>
          ) : (
            "Crear cuenta"
          )}
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-muted-foreground">
        ¿Ya tenés una cuenta?{" "}
        <Link href="/login" className="font-medium text-primary hover:underline">
          Iniciar sesión
        </Link>
      </p>
    </AuthShell>
  );
}