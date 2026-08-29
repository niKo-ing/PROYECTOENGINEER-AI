"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { SlidersHorizontal } from "lucide-react";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { flattenCategories } from "@/types/category";
import type { CategoryRead } from "@/types/category";

export const filterSchema = z.object({
  category: z.string().optional(),
  brand: z.string().optional(),
  min: z.string().optional(),
  max: z.string().optional(),
});

export type FilterValues = z.infer<typeof filterSchema>;

export const FILTER_LIMIT = 12;

export function getDefaultFilters(): FilterValues {
  return { category: "", brand: "", min: "", max: "" };
}

export function buildFilterQuery(values: FilterValues, page: number): string {
  const params = new URLSearchParams();
  if (values.brand && values.brand.trim()) params.set("brand", values.brand.trim());
  if (values.category && values.category.trim()) params.set("category", values.category.trim());
  if (values.min && values.min.trim()) params.set("min", values.min.trim());
  if (values.max && values.max.trim()) params.set("max", values.max.trim());
  params.set("page", String(page));
  return params.toString();
}

export function SearchFilters({ categories }: { categories: CategoryRead[] | undefined }) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const category = searchParams.get("category") ?? "";
  const brand = searchParams.get("brand") ?? "";
  const min = searchParams.get("min") ?? "";
  const max = searchParams.get("max") ?? "";

  const form = useForm<FilterValues>({
    resolver: zodResolver(filterSchema),
    defaultValues: { category, brand, min, max },
  });

  const { register, handleSubmit, setValue, watch } = form;
  const watched = watch([
    "category",
    "brand",
    "min",
    "max",
  ]) as [string, string, string, string];

  const urlValues = { category, brand, min, max };
  const hasActiveFilters = Boolean(category || brand || min || max);
  const hasDraftChanges = watched.some((value, index) => value.trim() !== Object.values(urlValues)[index].trim());

  const activeFilterLabels: { label: string; value: string }[] = [
    { label: "Categoría", value: category },
    { label: "Marca", value: brand },
    { label: "Mín", value: min },
    { label: "Máx", value: max },
  ];

  const flatCategories = categories ? flattenCategories(categories) : [];

  function applyFilters(values: FilterValues) {
    const q = searchParams.get("q") ?? "";
    const query = buildFilterQuery(values, 1);
    const prefix = q ? `q=${encodeURIComponent(q)}&` : "";
    router.push(`/search?${prefix}${query}`);
  }

  function resetFilters() {
    const q = searchParams.get("q") ?? "";
    router.push(q ? `/search?q=${encodeURIComponent(q)}&page=1` : "/search");
    form.reset(getDefaultFilters());
  }

  return (
    <form onSubmit={handleSubmit(applyFilters)} className="space-y-6">
      <div className="space-y-2">
        <Label htmlFor="category">Categoría</Label>
        <Select
          value={form.watch("category")}
          onValueChange={(value) => setValue("category", value, { shouldValidate: true })}
        >
          <SelectTrigger id="category" className="w-full">
            <SelectValue placeholder="Todas las categorías" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">Todas las categorías</SelectItem>
            {flatCategories.map((category) => (
              <SelectItem key={category.id} value={category.name}>
                {category.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="brand">Marca</Label>
        <Input id="brand" placeholder="Ej: Samsung, Apple…" {...register("brand")} />
      </div>

      <div className="space-y-2">
        <Label>Precio (CLP)</Label>
        <div className="flex items-center gap-2">
          <Input placeholder="Mín" inputMode="numeric" {...register("min")} />
          <span className="text-muted-foreground">—</span>
          <Input placeholder="Máx" inputMode="numeric" {...register("max")} />
        </div>
      </div>

      <Separator />

      <div className="flex items-center gap-2">
        <Button type="submit" className="flex-1" disabled={!hasActiveFilters && !hasDraftChanges}>
          Aplicar
        </Button>
        <Button type="button" variant="outline" onClick={resetFilters} disabled={!hasActiveFilters}>
          Limpiar
        </Button>
      </div>

      {hasActiveFilters ? (
        <div className="flex flex-wrap gap-2">
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <SlidersHorizontal className="h-3.5 w-3.5" />
            Filtros activos
          </span>
          {activeFilterLabels.map(
            (entry) =>
              entry.value && entry.value.trim() !== "" ? (
                <Badge key={entry.label} variant="secondary">
                  {entry.label}: {entry.value}
                </Badge>
              ) : null
          )}
        </div>
      ) : null}

      <p className="text-xs text-muted-foreground">
        Los filtros usan datos reales de la API. La categoría y lista completa se reflejan en
        las búsquedas.
      </p>
    </form>
  );
}
