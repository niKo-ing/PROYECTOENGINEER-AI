import type { ReactNode } from "react";

type AuthShellProps = {
  title: string;
  description: string;
  children: ReactNode;
};

export function AuthShell({ title, description, children }: AuthShellProps) {
  return (
    <main className="mx-auto w-full max-w-md px-4 py-10 sm:py-14">
      <section className="rounded-3xl border bg-card p-6 shadow-sm sm:p-8">
        <p className="text-sm font-medium text-primary">Tu sesión protege tus preferencias</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
        {children}
      </section>
    </main>
  );
}