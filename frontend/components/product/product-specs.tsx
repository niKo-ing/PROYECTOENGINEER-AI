"use client";

import { AlertCircle, ListChecks } from "lucide-react";

import type { CanonicalProductSpecs, ProductSpecs } from "@/types/product";

type DisplaySpecItem = {
  key?: string;
  label: string;
  value: string;
  value_kind?: string | null;
  value_json?: unknown;
  source_type?: string | null;
  source_name?: string | null;
  confidence?: number | null;
  verification_status?: string | null;
  conflict_status?: string | null;
};

type DisplaySpecSection = {
  title: string;
  items: DisplaySpecItem[];
};

const HUMAN_LABELS: Record<string, string> = {
  pcie_slot_list: "Ranuras PCI Express",
  m2_slot_list: "Slots M.2",
  rear_ports: "Puertos traseros",
  fan_header_list: "Headers de ventilación",
  cpu_power_connector_types: "Alimentación CPU",
  motherboard_power_connector: "Conector principal",
  auxiliary_power_connectors: "Conectores auxiliares",
  supported_cpu_generations: "Generaciones CPU",
  supported_memory_speeds: "Velocidades de memoria",
  overclock_memory_speeds: "Velocidades OC",
  front_panel_headers: "Headers del panel frontal",
  audio_features: "Características de audio",
  rgb_features: "Características RGB",
  onboard_buttons: "Botones integrados",
  dimensions: "Dimensiones",
};

const HIDDEN_WHEN_STRUCTURED: Record<string, string[]> = {
  pcie_slot_list: ["pcie_slots"],
  m2_slot_list: ["m2_slots"],
  fan_header_list: ["fan_headers_total", "cpu_fan_headers", "cpu_opt_headers", "pump_headers", "system_fan_headers"],
};

const SUMMARY_LIMIT = 8;
const SUMMARY_PRIORITY = [
  "gpu",
  "procesador",
  "vram",
  "ram",
  "memoria",
  "tipo de memoria",
  "almacenamiento",
  "pantalla",
  "panel",
  "tasa de refresco",
  "bus de memoria",
  "interfaz pcie",
  "frecuencias core",
  "frecuencia memoria",
  "consumo/tdp",
  "tdp",
  "fuente recomendada",
  "conector de poder",
  "salidas de video",
  "largo",
  "dimensiones",
];

function transformItems(items: CanonicalProductSpecs["sections"][number]["items"]): DisplaySpecItem[] {
  const presentKeys = new Set(items.map((item) => item.key));
  const hidden = new Set<string>();
  for (const item of items) {
    const derived = HIDDEN_WHEN_STRUCTURED[item.key] ?? [];
    for (const key of derived) {
      if (presentKeys.has(key)) hidden.add(key);
    }
  }
  return items
    .filter((item) => !hidden.has(item.key))
    .map((item) => ({
      key: item.key,
      label: HUMAN_LABELS[item.key] ?? item.label,
      value: item.value,
      value_kind: item.value_kind,
      value_json: item.value_json,
      source_type: item.source_type,
      source_name: item.source_name,
      confidence: item.confidence,
      verification_status: item.verification_status,
      conflict_status: item.conflict_status,
    }));
}

function getDisplaySections(canonicalSpecs?: CanonicalProductSpecs | null, specs?: ProductSpecs | null): DisplaySpecSection[] {
  const canonicalSections: DisplaySpecSection[] = (canonicalSpecs?.sections ?? [])
    .map((section) => ({ title: section.title, items: transformItems(section.items) }))
    .filter((section) => section.items?.length > 0);
  const fallbackSections: DisplaySpecSection[] = (specs?.sections ?? []).filter((section) => section.items?.length > 0);
  return canonicalSections.length ? canonicalSections : fallbackSections;
}

function cleanValue(value: string) {
  return value
    .replace(/\bYes x\s*/gi, "")
    .replace(/\bNo x\s*/gi, "No ")
    .replace(/\s*\(Native ([^)]+)\)/gi, " ($1)")
    .replace(/\s+/g, " ")
    .trim();
}

function formatDisplayValue(item: DisplaySpecItem) {
  if (item.value_kind === "json" && Array.isArray(item.value_json)) {
    const objects = item.value_json.filter((row): row is Record<string, unknown> => typeof row === "object" && row !== null);
    const labels = objects
      .map((row) => {
        const title = row.type ?? row.kind ?? row.interface ?? row.header ?? row.btn;
        const count = typeof row.count === "number" || typeof row.count === "string" ? `${row.count} x ` : "";
        return title ? `${count}${String(title)}` : "";
      })
      .filter(Boolean);
    if (labels.length) return labels.join(", ");
  }

  return cleanValue(item.value);
}

function formatSummaryValue(value: string) {
  const cleaned = cleanValue(value);
  if (cleaned.length <= 72) return normalizeCapacitySpacing(cleaned);

  const parts = cleaned.split(/,\s*/).filter(Boolean);
  if (parts.length > 2) return `${parts.slice(0, 2).join(", ")} +${parts.length - 2} más`;

  return `${cleaned.slice(0, 69).trim()}…`;
}

function summaryLabel(label: string) {
  const normalized = normalizeLabel(label);

  if (normalized.includes("frecuencia pantalla") || normalized.includes("tasa de refresco")) {
    return "Tasa de refresco";
  }
  if (normalized.includes("frecuencia") && !normalized.includes("memoria")) {
    return "Frecuencias core";
  }
  if (normalized.includes("memoria") && normalized.includes("frecuencia")) {
    return "Frecuencia memoria";
  }
  if (normalized === "bus" || normalized.includes("bus de memoria")) {
    return "Bus de memoria";
  }
  if (normalized.includes("capacidad almacenamiento")) {
    return "Almacenamiento";
  }
  if (normalized.includes("tamano pantalla")) {
    return "Pantalla";
  }
  if (normalized.includes("tipo de panel")) {
    return "Panel";
  }
  if (normalized === "interfaz" || normalized.includes("pcie")) {
    return "Interfaz PCIe";
  }
  if (normalized.includes("salidas de video") || normalized.includes("puertos de video")) {
    return "Salidas de video";
  }
  return label;
}

function buildSummaryItems(canonicalSpecs?: CanonicalProductSpecs | null, specs?: ProductSpecs | null) {
  const seen = new Set<string>();
  const items: Array<{ label: string; value: string }> = [];

  for (const section of getDisplaySections(canonicalSpecs, specs)) {
    for (const item of section.items) {
      const rawValue = formatDisplayValue(item);
      if (shouldSkipSummaryItem(item.label, rawValue)) continue;

      const value = formatSummaryValue(rawValue);
      const label = summaryLabel(item.label);
      const key = `${label}:${value}`.toLowerCase();
      if (!value || seen.has(key)) continue;
      seen.add(key);
      items.push({ label, value });
    }
  }

  return items;
}

function shouldSkipSummaryItem(label: string, value: string) {
  const normalized = normalizeLabel(label);
  if (normalized === "pantalla" && value.length > 72) return true;
  if (normalized.includes("camara") && value.length > 72) return true;
  if (normalized.includes("bateria") && value.toLowerCase().includes("si/c")) return true;
  return false;
}

function deriveSpecsFromName(name?: string | null) {
  if (!name) return [];
  const items: Array<{ label: string; value: string }> = [];

  const gpu = name.match(/\b(?:NVIDIA\s+)?GeForce\s+(?:RTX|GTX)\s*[A-Z]?\s*\d{3,4}(?:\s*Ti)?\b/i);
  if (gpu) items.push({ label: "GPU", value: cleanValue(gpu[0].replace(/\s+/g, " ")) });

  const cpu = name.match(/\b(?:Intel\s+)?Core\s+i[3579][-\s]?\d{3,5}[A-Z]*\b|\b(?:AMD\s+)?Ryzen\s+[3579]\s+\d{4}[A-Z]*\b/i);
  if (cpu) items.push({ label: "Procesador", value: cleanValue(cpu[0].replace(/\s+/g, " ")) });

  const memory = name.match(/\b(\d+)\s*GB\s+(DDR[345]|GDDR[56X]*)\b/i);
  if (memory) {
    const capacity = `${memory[1]} GB`;
    const memoryType = memory[2].toUpperCase();
    if (/GDDR/i.test(memoryType)) {
      items.push({ label: "VRAM", value: capacity });
    } else {
      items.push({ label: "RAM", value: capacity });
    }
    items.push({ label: "Tipo de memoria", value: memoryType });
  }

  const standaloneRam = name.match(/\b\d+\s*GB\s+RAM\b/i);
  if (standaloneRam && !items.some((item) => item.label === "RAM")) {
    items.push({ label: "RAM", value: cleanValue(standaloneRam[0].replace(/\s*RAM/i, "").replace(/(\d+)\s*GB/i, "$1 GB")) });
  }

  const storage = name.match(/\b(?:\d+\s*(?:GB|TB)\s*)?(?:SSD|HDD|NVMe)\b/i);
  if (storage) items.push({ label: "Almacenamiento", value: cleanValue(storage[0].replace(/(\d+)\s*(GB|TB)/i, "$1 $2").toUpperCase()) });

  const titleStorage = name.match(/\b(\d+)\s*(GB|TB)\s+(?:ROM|almacenamiento)\b/i) ?? name.match(/\b(\d+)(GB|TB)\s+Rom\b/i);
  if (titleStorage) items.push({ label: "Almacenamiento", value: `${titleStorage[1]} ${titleStorage[2].toUpperCase()}` });

  const bus = name.match(/\b\d{2,4}[-\s]?bit\b/i);
  if (bus) items.push({ label: "Bus de memoria", value: cleanValue(bus[0].replace(/[-\s]?bit/i, " bit")) });

  const pcie = name.match(/\bPCI[-\s]?e\s*(\d(?:\.\d)?)\s*x\s*(\d{1,2})\b/i);
  if (pcie) items.push({ label: "Interfaz PCIe", value: `PCIe ${pcie[1]} x${pcie[2]}` });

  const screen = name.match(/\b\d{1,2}(?:[.,]\d)?\s*(?:"|pulgadas?|inch|in)\b/i);
  if (screen) items.push({ label: "Pantalla", value: cleanValue(screen[0].replace(",", ".")) });

  const screenWithPanel = name.match(/\b(\d{1,2}(?:[.,]\d)?)\s*(AMOLED|OLED|LCD|IPS|LED)\b/i);
  if (screenWithPanel) {
    if (!items.some((item) => item.label === "Pantalla")) {
      items.push({ label: "Pantalla", value: `${screenWithPanel[1].replace(",", ".")}"` });
    }
    items.push({ label: "Panel", value: screenWithPanel[2].toUpperCase() });
  }

  const refreshRate = name.match(/\b\d{2,3}\s*Hz\b/i);
  if (refreshRate) items.push({ label: "Tasa de refresco", value: cleanValue(refreshRate[0].replace(/\s+/g, " ")) });

  const coreFrequencies = name.match(/\b\d{3,5}\s*(?:\/\s*\d{3,5}){1,3}\s*MHz\b/i);
  if (coreFrequencies) items.push({ label: "Frecuencias core", value: cleanValue(coreFrequencies[0].replace(/\s*\/\s*/g, " / ")) });

  return items;
}

export function ProductFeatureSummary({
  name,
  brand,
  category,
  canonicalSpecs,
  specs,
}: {
  name?: string | null;
  brand?: string | null;
  category?: string | null;
  canonicalSpecs?: CanonicalProductSpecs | null;
  specs: ProductSpecs | null;
}) {
  const specItems = mergeSummaryItems(deriveSpecsFromName(name), buildSummaryItems(canonicalSpecs, specs));
  const identityItems = [
    brand ? { label: "Fabricante", value: brand } : null,
    category ? { label: "Categoría", value: category } : null,
  ].filter((item): item is { label: string; value: string } => Boolean(item));
  const primaryItems = mergeSummaryItems(identityItems, specItems).slice(0, SUMMARY_LIMIT);

  if (!primaryItems.length) return null;

  return (
    <section className="mt-6 border-t pt-5">
      <h2 className="text-sm font-semibold tracking-tight text-foreground">Características clave</h2>
      <dl className="mt-3 grid gap-x-5 gap-y-2 text-sm leading-5 sm:grid-cols-2">
        {primaryItems.map((item, index) => (
          <div key={`${normalizeLabel(item.label)}-${normalizeLabel(item.value)}-${index}`} className="min-w-0 rounded-lg bg-muted/30 px-3 py-2">
            <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{item.label}</dt>
            <dd className="mt-0.5 min-w-0 break-words font-semibold text-foreground">{item.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function normalizeCapacitySpacing(value: string) {
  return value.replace(/\b(\d+)\s*(GB|TB|MB)\b/gi, (_, amount: string, unit: string) => `${amount} ${unit.toUpperCase()}`);
}

function mergeSummaryItems(...groups: Array<Array<{ label: string; value: string }>>) {
  const merged: Array<{ label: string; value: string }> = [];

  for (const item of groups.flat()) {
    const label = summaryLabel(item.label);
    const value = cleanValue(item.value);
    if (!value) continue;
    const existing = merged.find((current) => normalizeLabel(current.label) === normalizeLabel(label));
    if (!existing) {
      merged.push({ label, value });
      continue;
    }

    existing.value = mergeDisplayValues(existing.label, existing.value, value);
  }

  return merged.sort((a, b) => summaryRank(a.label) - summaryRank(b.label));
}

function mergeDisplayValues(label: string, currentValue: string, nextValue: string) {
  const current = cleanValue(currentValue);
  const next = cleanValue(nextValue);
  const currentKey = current.toLowerCase();
  const nextKey = next.toLowerCase();

  if (currentKey === nextKey) return current;
  if (currentKey.includes(nextKey)) return current;
  if (nextKey.includes(currentKey)) return next;

  if (normalizeLabel(label) === "frecuencias core") {
    const mhzValues = Array.from(
      new Set([current, next].join(" / ").match(/\d{3,5}\s*MHz/gi)?.map((value) => value.replace(/\s*MHz/i, "")) ?? []),
    );
    if (mhzValues.length > 1) return `${mhzValues.join(" / ")} MHz`;
  }

  const values = current.split(" / ").map((value) => value.trim());
  if (values.some((value) => value.toLowerCase() === nextKey || value.toLowerCase().includes(nextKey) || nextKey.includes(value.toLowerCase()))) {
    return current;
  }
  return `${current} / ${next}`;
}

function summaryRank(label: string) {
  const normalized = normalizeLabel(label);
  const index = SUMMARY_PRIORITY.findIndex((item) => normalizeLabel(item) === normalized);
  return index === -1 ? SUMMARY_PRIORITY.length : index;
}

function normalizeLabel(label: string) {
  return label
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function needsReview(item: DisplaySpecItem) {
  if (!item.verification_status && !item.conflict_status) return false;
  const fromAi = item.source_type === "ai" || item.source_type === "ai_research";
  return (
    item.conflict_status === "pending" ||
    (fromAi && item.verification_status !== "verified" && (!item.source_name || item.confidence === null || item.confidence === undefined || item.confidence < 0.75))
  );
}

function reviewTitle(item: DisplaySpecItem) {
  if (item.conflict_status === "pending") return "Dato con conflicto pendiente de revisión";
  if (item.source_type === "ai" || item.source_type === "ai_research") return "Dato generado con IA pendiente de verificación";
  if (item.verification_status === "review") return "Dato pendiente de verificación";
  return "Dato pendiente de verificación";
}


export function SpecHighlights({ specs }: { specs: ProductSpecs | null }) {
  if (!specs?.highlights?.length) return null;

  return (
    <div className="mt-6 border-b pb-6">
      <p className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Características clave
      </p>
      <ul className="flex flex-wrap gap-2">
        {specs.highlights.map((highlight) => (
          <li
            key={highlight}
            className="rounded-lg border bg-muted/50 px-3.5 py-2.5 text-sm font-semibold leading-5 text-foreground"
          >
            {highlight}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SpecSheet({ canonicalSpecs, specs }: { canonicalSpecs?: CanonicalProductSpecs | null; specs: ProductSpecs | null }) {
  const sections = getDisplaySections(canonicalSpecs, specs);
  if (!sections.length) return null;

  return (
    <div>
      <div className="border-b bg-muted/20 p-5">
        <h2 className="flex items-center gap-2 text-lg font-semibold leading-none tracking-tight">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <ListChecks className="size-4" aria-hidden="true" />
          </span>
          Ficha técnica completa
        </h2>
      </div>
      <div className="p-0">
        <div className="grid lg:grid-cols-2">
          {sections.map((section) => (
            <section
              key={section.title}
              aria-label={section.title}
              className="min-w-0 border-b p-5 odd:lg:border-r"
            >
              <h3 className="mb-2 text-sm font-semibold tracking-tight text-foreground">{section.title}</h3>
              <dl className="divide-y divide-border/70">
                {section.items.map((item) => (
                  <div
                    key={`${section.title}-${item.label}-${item.value}`}
                    className="grid gap-x-6 gap-y-1.5 py-3 first:pt-1 last:pb-0 sm:grid-cols-[minmax(10rem,0.65fr)_minmax(0,1.35fr)]"
                  >
                    <dt className="min-w-0 text-sm leading-relaxed text-muted-foreground">
                      {item.label}
                    </dt>
                    <dd className="min-w-0 space-y-1.5">
                      {item.value_kind === "json" && Array.isArray(item.value_json) && item.value_json.some((row) => typeof row === "object" && row !== null) ? (
                        <div className="flex min-w-0 items-start gap-2">
                          <StructuredSpecValue rows={item.value_json} />
                          {needsReview(item) ? <ReviewIndicator item={item} /> : null}
                        </div>
                      ) : (
                        <div className="flex min-w-0 items-start gap-2">
                          <span className="min-w-0 break-words text-sm font-semibold leading-relaxed text-foreground">
                            {formatDisplayValue(item)}
                          </span>
                          {needsReview(item) ? <ReviewIndicator item={item} /> : null}
                        </div>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}

function ReviewIndicator({ item }: { item: DisplaySpecItem }) {
  const conflict = item.conflict_status === "pending";
  return (
    <span
      className={`mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full ${conflict ? "bg-amber-100 text-amber-700" : "bg-sky-100 text-sky-700"}`}
      title={reviewTitle(item)}
      aria-label={reviewTitle(item)}
    >
      <AlertCircle className="size-3.5" aria-hidden="true" />
    </span>
  );
}

function structuredLabel(key: string): string {
  const labels: Record<string, string> = {
    type: "Tipo",
    kind: "Tipo",
    interface: "Interfaz",
    generation: "Gen.",
    version: "Versión",
    lanes: "Líneas",
    count: "Cant.",
    pins: "Pines",
    form_factors: "Formatos",
    feat: "Detalle",
    header: "Header",
    btn: "Botón",
    val: "Valor",
  };
  return labels[key] ?? key;
}

function StructuredSpecValue({ rows }: { rows: unknown[] }) {
  const objects = rows.filter((row): row is Record<string, unknown> => typeof row === "object" && row !== null);
  const keys = Array.from(new Set(objects.flatMap((row) => Object.keys(row)))).filter((key) => key !== "type");
  const labelKey = objects.some((row) => "type" in row) ? "type" : objects.some((row) => "kind" in row) ? "kind" : objects.some((row) => "interface" in row) ? "interface" : keys[0];

  return (
    <div className="grid gap-1.5">
      {objects.map((row, index) => {
        const title = row[labelKey];
        const cells = keys.filter((key) => row[key] !== null && row[key] !== undefined && row[key] !== "" && !(Array.isArray(row[key]) && row[key].length === 0));
        return (
          <div key={index} className="text-sm leading-relaxed">
            <span className="font-semibold text-foreground">{typeof title === "string" ? title : String(title ?? "")}</span>
            {cells.length ? (
              <span className="ml-2 text-muted-foreground">{cells.map((key) => `${structuredLabel(key)}: ${Array.isArray(row[key]) ? (row[key] as string[]).join(", ") : String(row[key])}`).join(" · ")}</span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
