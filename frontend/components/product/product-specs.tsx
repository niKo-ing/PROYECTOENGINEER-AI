"use client";

import { ListChecks } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ProductSpecs } from "@/types/product";

export function SpecHighlights({ specs }: { specs: ProductSpecs | null }) {
  if (!specs?.highlights?.length) return null;

  return (
    <div className="mt-5 border-b pb-5">
      <p className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Características clave
      </p>
      <ul className="flex flex-wrap gap-2">
        {specs.highlights.map((highlight) => (
          <li
            key={highlight}
            className="rounded-lg border bg-muted/50 px-3 py-2 text-xs font-semibold text-foreground"
          >
            {highlight}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SpecSheet({ specs }: { specs: ProductSpecs | null }) {
  const sections = (specs?.sections ?? []).filter((section) => section.items?.length > 0);
  if (!sections.length) return null;

  return (
    <Card className="mt-6 shadow-none">
      <CardHeader className="pb-4">
        <CardTitle className="flex items-center gap-2 text-base">
          <ListChecks className="size-4 text-primary" aria-hidden="true" />
          Ficha técnica
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid gap-x-12 gap-y-9 md:grid-cols-2">
          {sections.map((section) => (
            <section key={section.title} aria-label={section.title}>
              <h3 className="mb-2 border-b pb-2 text-sm font-semibold text-foreground">
                {section.title}
              </h3>
              <dl>
                {section.items.map((item) => (
                  <div
                    key={`${section.title}-${item.label}`}
                    className="grid gap-x-6 gap-y-1 border-b py-2.5 last:border-0 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]"
                  >
                    <dt className="min-w-0 text-sm leading-relaxed text-muted-foreground">
                      {item.label}
                    </dt>
                    <dd className="min-w-0 break-words text-sm font-medium leading-relaxed text-foreground">
                      {item.value}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}