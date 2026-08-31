import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { formatCLPCompact } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { CategoryFacets } from "@/types/catalog";

export interface SpecRangeValue {
  min: number | null;
  max: number | null;
}

export interface FilterState {
  brand: string[];
  minPrice: number | null;
  maxPrice: number | null;
  spec: Record<string, string[]>;
  ranges: Record<string, SpecRangeValue>;
}

export const EMPTY_FILTERS: FilterState = { brand: [], minPrice: null, maxPrice: null, spec: {}, ranges: {} };

export function hasActiveFilters(filters: FilterState): boolean {
  if (filters.brand.length > 0 || filters.minPrice !== null || filters.maxPrice !== null) return true;
  if (Object.values(filters.spec).some((values) => values.length > 0)) return true;
  return Object.values(filters.ranges).some((range) => range.min !== null || range.max !== null);
}

export function serializeFilters(filters: FilterState): string | undefined {
  if (!hasActiveFilters(filters)) return undefined;
  return JSON.stringify(filters);
}

export function parseFilters(payload: string | null): FilterState {
  if (!payload) return EMPTY_FILTERS;
  try {
    const parsed: unknown = JSON.parse(payload);
    if (parsed && typeof parsed === "object") {
      const raw = parsed as Record<string, unknown>;
      const brand = Array.isArray(raw.brand) ? raw.brand.filter((item): item is string => typeof item === "string") : [];
      const spec: Record<string, string[]> = {};
      if (raw.spec && typeof raw.spec === "object") {
        for (const [key, values] of Object.entries(raw.spec)) {
          if (Array.isArray(values)) spec[key] = values.filter((item): item is string => typeof item === "string");
        }
      }
      const ranges: Record<string, SpecRangeValue> = {};
      if (raw.ranges && typeof raw.ranges === "object") {
        for (const [key, value] of Object.entries(raw.ranges)) {
          if (value && typeof value === "object") {
            const range = value as Record<string, unknown>;
            ranges[key] = {
              min: typeof range.min === "number" ? range.min : null,
              max: typeof range.max === "number" ? range.max : null,
            };
          }
        }
      }
      return {
        brand,
        minPrice: typeof raw.minPrice === "number" ? raw.minPrice : null,
        maxPrice: typeof raw.maxPrice === "number" ? raw.maxPrice : null,
        spec,
        ranges,
      };
    }
  } catch {
    // ignore malformed payload
  }
  return EMPTY_FILTERS;
}

export function buildSpecFilterQueries(filters: FilterState): { spec_filters?: string; spec_ranges?: string } {
  const result: { spec_filters?: string; spec_ranges?: string } = {};
  const textFilters: Record<string, string> = {};
  for (const [key, values] of Object.entries(filters.spec)) {
    if (values.length > 0) textFilters[key] = values.join(",");
  }
  if (Object.keys(textFilters).length > 0) result.spec_filters = JSON.stringify(textFilters);
  const ranges: Record<string, string> = {};
  for (const [key, range] of Object.entries(filters.ranges)) {
    if (range.min === null && range.max === null) continue;
    ranges[key] = `${range.min ?? ""}-${range.max ?? ""}`;
  }
  if (Object.keys(ranges).length > 0) result.spec_ranges = JSON.stringify(ranges);
  return result;
}

interface CategoryFiltersProps {
  facets?: CategoryFacets;
  value: FilterState;
  onChange: (next: FilterState) => void;
  onClear: () => void;
  isLoading?: boolean;
}

export function CategoryFilters({ facets, value, onChange, onClear, isLoading }: CategoryFiltersProps) {
  const active = hasActiveFilters(value);

  function toggleBrand(brandValue: string) {
    const brand = value.brand.includes(brandValue)
      ? value.brand.filter((item) => item !== brandValue)
      : [...value.brand, brandValue];
    onChange({ ...value, brand });
  }

  function toggleSpec(key: string, optionValue: string) {
    const current = value.spec[key] ?? [];
    const next = current.includes(optionValue)
      ? current.filter((item) => item !== optionValue)
      : [...current, optionValue];
    onChange({ ...value, spec: { ...value.spec, [key]: next } });
  }

  const brandCounts = new Map((facets?.brands ?? []).map((option) => [option.value, option.count]));
  const brands = facets?.brands ?? [];

  return (
    <div className="space-y-6">
      <section>
        <FilterHeading title="Marca" />
        {isLoading ? (
          <FilterListSkeleton rows={3} />
        ) : brands.length > 0 ? (
          <FilterList>
            {brands.map((option) => (
              <CheckboxRow
                key={option.value}
                label={option.value}
                count={option.count}
                checked={value.brand.includes(option.value)}
                onToggle={() => toggleBrand(option.value)}
              />
            ))}
          </FilterList>
        ) : (
          <p className="text-xs text-muted-foreground">Sin marcas disponibles.</p>
        )}
      </section>

      <section>
        <FilterHeading title="Precio (CLP)" />
        <div className="flex items-center gap-2">
          <MoneyInput
            key={`price-min-${value.minPrice}`}
            value={value.minPrice}
            placeholder={facets?.price_range?.minimum ? formatCLPCompact(facets.price_range.minimum) : "Mín"}
            ariaLabel="Precio mínimo"
            onCommit={(minimum) => onChange({ ...value, minPrice: minimum })}
          />
          <span className="text-muted-foreground" aria-hidden="true">
            —
          </span>
          <MoneyInput
            key={`price-max-${value.maxPrice}`}
            value={value.maxPrice}
            placeholder={facets?.price_range?.maximum ? formatCLPCompact(facets.price_range.maximum) : "Máx"}
            ariaLabel="Precio máximo"
            onCommit={(maximum) => onChange({ ...value, maxPrice: maximum })}
          />
        </div>
      </section>

      {isLoading
        ? Array.from({ length: 2 }).map((_, index) => <FilterListSkeleton key={index} rows={2} />)
        : facets?.specs.map((spec) =>
            spec.kind === "range" ? (
              <section key={spec.key}>
                <FilterHeading title={spec.label} />
                <div className="flex items-center gap-2">
                  <NumberInput
                    key={`${spec.key}-min-${value.ranges[spec.key]?.min ?? ""}`}
                    value={value.ranges[spec.key]?.min ?? null}
                    placeholder={spec.range?.minimum != null ? String(spec.range.minimum) : "Mín"}
                    ariaLabel={`${spec.label} mínimo`}
                    unit={spec.unit}
                    onCommit={(minimum) =>
                      onChange({
                        ...value,
                        ranges: { ...value.ranges, [spec.key]: { min: minimum, max: value.ranges[spec.key]?.max ?? null } },
                      })
                    }
                  />
                  <span className="text-muted-foreground" aria-hidden="true">
                    —
                  </span>
                  <NumberInput
                    key={`${spec.key}-max-${value.ranges[spec.key]?.max ?? ""}`}
                    value={value.ranges[spec.key]?.max ?? null}
                    placeholder={spec.range?.maximum != null ? String(spec.range.maximum) : "Máx"}
                    ariaLabel={`${spec.label} máximo`}
                    unit={spec.unit}
                    onCommit={(maximum) =>
                      onChange({
                        ...value,
                        ranges: { ...value.ranges, [spec.key]: { min: value.ranges[spec.key]?.min ?? null, max: maximum } },
                      })
                    }
                  />
                </div>
              </section>
            ) : (
              <section key={spec.key}>
                <FilterHeading title={spec.label} />
                <FilterList>
                  {spec.options.map((option) => (
                    <CheckboxRow
                      key={option.value}
                      label={option.value}
                      count={option.count}
                      checked={(value.spec[spec.key] ?? []).includes(option.value)}
                      onToggle={() => toggleSpec(spec.key, option.value)}
                    />
                  ))}
                </FilterList>
              </section>
            )
          )}

      {active ? (
        <Button type="button" variant="ghost" size="sm" onClick={onClear} className="w-full">
          Limpiar filtros
        </Button>
      ) : null}
    </div>
  );
}

function FilterHeading({ title }: { title: string }) {
  return (
    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>
  );
}

function FilterList({ children }: { children: React.ReactNode }) {
  return <div className="max-h-56 space-y-1 overflow-y-auto pr-1">{children}</div>;
}

function CheckboxRow({
  label,
  count,
  checked,
  onToggle,
}: {
  label: string;
  count?: number;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 transition-colors hover:bg-accent">
      <Checkbox checked={checked} onCheckedChange={onToggle} aria-label={label} />
      <span className="flex-1 truncate text-sm">{label}</span>
      {count !== undefined ? (
        <Badge variant="secondary" className="rounded-full px-1.5 py-0 text-[10px] font-normal">
          {count}
        </Badge>
      ) : null}
    </label>
  );
}

function MoneyInput({
  value,
  placeholder,
  ariaLabel,
  onCommit,
}: {
  value: number | null;
  placeholder?: string;
  ariaLabel: string;
  onCommit: (value: number | null) => void;
}) {
  return (
    <NumberDraft
      value={value}
      placeholder={placeholder}
      ariaLabel={ariaLabel}
      prefix="$ "
      width="w-full"
      onCommit={onCommit}
    />
  );
}

function NumberInput({
  value,
  placeholder,
  ariaLabel,
  unit,
  onCommit,
}: {
  value: number | null;
  placeholder?: string;
  ariaLabel: string;
  unit?: string | null;
  onCommit: (value: number | null) => void;
}) {
  return (
    <div className="flex w-full items-center gap-1">
      <NumberDraft value={value} placeholder={placeholder} ariaLabel={ariaLabel} width="w-full" onCommit={onCommit} />
      {unit ? <span className="text-xs text-muted-foreground">{unit}</span> : null}
    </div>
  );
}

function NumberDraft({
  value,
  placeholder,
  ariaLabel,
  prefix,
  width,
  onCommit,
}: {
  value: number | null;
  placeholder?: string;
  ariaLabel: string;
  prefix?: string;
  width?: string;
  onCommit: (value: number | null) => void;
}) {
  const [draft, setDraft] = useState(value === null ? "" : String(value));

  return (
    <div className={cn("relative", width)}>
      {prefix ? (
        <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
          {prefix}
        </span>
      ) : null}
      <Input
        type="text"
        inputMode="numeric"
        value={draft}
        placeholder={placeholder}
        aria-label={ariaLabel}
        onChange={(event) => setDraft(event.target.value.replace(/[^\d.]/g, ""))}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.currentTarget.blur();
          }
        }}
        className={cn("h-9", prefix && "pl-7", "tabular-nums")}
      />
    </div>
  );

  function commit() {
    const trimmed = draft.trim();
    const next = trimmed === "" ? null : Number(trimmed.replace(",", "."));
    const normalized: number | null = next !== null && Number.isFinite(next) ? next : null;
    const changed = value !== normalized;
    setDraft(normalized === null ? "" : String(normalized));
    if (changed) onCommit(normalized);
  }
}

function FilterListSkeleton({ rows }: { rows: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className={cn("h-6 animate-pulse rounded-md bg-muted")} />
      ))}
    </div>
  );
}