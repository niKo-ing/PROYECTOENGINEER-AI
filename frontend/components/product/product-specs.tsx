"use client";

import { AlertTriangle, Bot, CheckCircle2, Database, Factory, ListChecks, PenTool, ShieldCheck, Store, WandSparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CanonicalProductSpecs, ProductSpecs } from "@/types/product";

type DisplaySpecItem = {
  key?: string;
  label: string;
  value: string;
  source_type?: string | null;
  source_name?: string | null;
  verification_status?: string | null;
  conflict_status?: string | null;
};

type DisplaySpecSection = {
  title: string;
  items: DisplaySpecItem[];
};

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

export function SpecSheet({ canonicalSpecs, specs }: { canonicalSpecs?: CanonicalProductSpecs | null; specs: ProductSpecs | null }) {
  const canonicalSections: DisplaySpecSection[] = (canonicalSpecs?.sections ?? []).filter((section) => section.items?.length > 0);
  const fallbackSections: DisplaySpecSection[] = (specs?.sections ?? []).filter((section) => section.items?.length > 0);
  const sections = canonicalSections.length ? canonicalSections : fallbackSections;
  if (!sections.length) return null;
  const hasCanonical = canonicalSections.length > 0;

  return (
    <Card className="mt-6 overflow-hidden border-muted shadow-none">
      <CardHeader className="border-b bg-muted/30 pb-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <span className="flex size-8 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <ListChecks className="size-4" aria-hidden="true" />
            </span>
            Ficha técnica
          </CardTitle>
          {hasCanonical ? (
            <Badge variant="secondary" className="gap-1.5 rounded-full px-3 py-1 text-xs">
              <ShieldCheck className="size-3.5" aria-hidden="true" />
              Specs canónicas
            </Badge>
          ) : (
            <Badge variant="outline" className="rounded-full px-3 py-1 text-xs">
              Ficha JSON heredada
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="p-4 sm:p-5">
        <div className="grid gap-4 lg:grid-cols-2">
          {sections.map((section) => (
            <section
              key={section.title}
              aria-label={section.title}
              className="rounded-2xl border bg-background/80 p-4 transition-colors hover:border-primary/30"
            >
              <div className="mb-3 flex items-center justify-between gap-3 border-b pb-2.5">
                <h3 className="text-sm font-semibold tracking-tight text-foreground">
                  {section.title}
                </h3>
                <span className="text-xs text-muted-foreground">
                  {section.items.length} {section.items.length === 1 ? "dato" : "datos"}
                </span>
              </div>
              <dl className="divide-y divide-border/70">
                {section.items.map((item) => (
                  <div
                    key={`${section.title}-${item.label}-${item.value}`}
                    className="group grid gap-x-6 gap-y-1.5 py-3 first:pt-0 last:pb-0 sm:grid-cols-[minmax(8rem,0.8fr)_minmax(0,1.4fr)]"
                  >
                    <dt className="min-w-0 text-sm leading-relaxed text-muted-foreground">
                      {item.label}
                    </dt>
                    <dd className="min-w-0 space-y-1.5">
                      <div className="break-words text-sm font-semibold leading-relaxed text-foreground">
                        {item.value}
                      </div>
                      {hasCanonical ? <SpecMeta item={item} /> : null}
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

function SpecMeta({ item }: { item: DisplaySpecItem }) {
  const isConflict = item.conflict_status === "pending";
  const verification = verificationLabel(item.verification_status);
  const source = sourceLabel(item.source_type, item.source_name);
  if (!verification && !source && !isConflict) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5 opacity-80 transition-opacity group-hover:opacity-100">
      {isConflict ? (
        <Badge variant="outline" className="gap-1 border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-700" title="Hay un valor entrante distinto pendiente de revisión">
          <AlertTriangle className="size-3" aria-hidden="true" />
          conflicto
        </Badge>
      ) : null}
      {verification ? (
        <Badge variant="outline" className={verification.className} title={verification.title}>
          <verification.Icon className="size-3" aria-hidden="true" />
          {verification.label}
        </Badge>
      ) : null}
      {source ? (
        <Badge variant="outline" className="gap-1 border-transparent bg-muted/70 px-2 py-0.5 text-[11px] text-muted-foreground" title={source.title}>
          <source.Icon className="size-3" aria-hidden="true" />
          {source.label}
        </Badge>
      ) : null}
    </div>
  );
}

function verificationLabel(status?: string | null) {
  if (status === "verified") {
    return {
      label: "verificado",
      title: "Dato revisado por una persona",
      Icon: CheckCircle2,
      className: "gap-1 border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700",
    };
  }
  if (status === "review") {
    return {
      label: "por revisar",
      title: "Dato extraído automáticamente pendiente de revisión humana",
      Icon: ShieldCheck,
      className: "gap-1 border-sky-200 bg-sky-50 px-2 py-0.5 text-[11px] text-sky-700",
    };
  }
  if (status === "auto") {
    return {
      label: "auto",
      title: "Dato generado o extraído automáticamente",
      Icon: WandSparkles,
      className: "gap-1 border-transparent bg-muted/70 px-2 py-0.5 text-[11px] text-muted-foreground",
    };
  }
  return null;
}

function sourceLabel(type?: string | null, name?: string | null) {
  if (!type) return null;
  const label = name || sourceTypeLabel(type);
  const title = name ? `${sourceTypeLabel(type)}: ${name}` : sourceTypeLabel(type);
  const Icon = type === "manufacturer" ? Factory : type === "store" ? Store : type === "admin" ? PenTool : type === "ai" ? Bot : Database;
  return { label, title, Icon };
}

function sourceTypeLabel(type: string) {
  const labels: Record<string, string> = {
    ai: "IA",
    admin: "Admin",
    manufacturer: "Fabricante",
    store: "Tienda",
    scraper: "Scraper",
    ingestion: "Ingesta",
    external: "Fuente externa",
  };
  return labels[type] ?? type;
}
