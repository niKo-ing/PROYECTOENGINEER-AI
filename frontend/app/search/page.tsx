"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useDeferredValue, useEffect, useMemo, useState } from "react";
import { Search, SlidersHorizontal } from "lucide-react";

import { ProductGrid, ProductGridSkeleton } from "@/components/product/product-grid";
import { EmptyState } from "@/components/product/empty-state";
import { SearchFilters } from "@/components/search/search-filters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useCategories, useProducts } from "@/hooks/use-catalog";
import { FILTER_LIMIT, buildFilterQuery } from "@/components/search/search-filters";

export default function SearchPage() {
  return (
    <Suspense fallback={<SearchPageSkeleton />}>
      <SearchContent />
    </Suspense>
  );
}

function SearchContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const q = searchParams.get("q") ?? "";
  const category = searchParams.get("category") ?? "";
  const brand = searchParams.get("brand") ?? "";
  const min = searchParams.get("min") ?? "";
  const max = searchParams.get("max") ?? "";
  const pageRaw = Number(searchParams.get("page") ?? "1");
  const page = Number.isFinite(pageRaw) && pageRaw > 0 ? pageRaw : 1;

  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);

  const categoriesQuery = useCategories();
  const productsQuery = useProducts({
    query: q || undefined,
    category: category || undefined,
    brand: brand || undefined,
    min_price_clp: parseInteger(min) || undefined,
    max_price_clp: parseInteger(max) || undefined,
    limit: FILTER_LIMIT,
    offset: (page - 1) * FILTER_LIMIT,
  });

  const total = productsQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / FILTER_LIMIT));

  function goToPage(nextPage: number) {
    const next = Math.min(Math.max(1, nextPage), totalPages);
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    const filterQuery = buildFilterQuery(
      { category, brand, min, max },
      next
    );
    const combined = `${params.toString() ? params.toString() + "&" : ""}${filterQuery}`;
    router.push(`/search?${combined}`);
  }

  const hasActiveFilters = Boolean(category || brand || min || max);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
          {q ? (
            <>
              Resultados para <span className="text-primary">“{q}”</span>
            </>
          ) : (
            <>Explorar productos</>
          )}
        </h1>
        <div className="mt-4 flex items-center gap-2">
          <DebouncedSearchBar initialValue={q} />
          <Button
            variant="outline"
            className="gap-2 lg:hidden"
            onClick={() => setMobileFiltersOpen(true)}
          >
            <SlidersHorizontal className="h-4 w-4" />
            Filtros
          </Button>
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-[240px_1fr]">
        <aside className="hidden lg:block">
          <div className="sticky top-20 rounded-xl border bg-card p-4">
            <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
              <SlidersHorizontal className="h-4 w-4" />
              Filtros
            </h2>
            <SearchFilters categories={categoriesQuery.data} />
          </div>
        </aside>

        <div>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              {productsQuery.isLoading ? "Buscando…" : `${total} producto${total === 1 ? "" : "s"} encontrado${total === 1 ? "" : "s"}`}
            </p>
            <div className="flex items-center gap-2">
              {hasActiveFilters ? (
                <Badge variant="secondary">Filtros activos</Badge>
              ) : null}
            </div>
          </div>

          {productsQuery.isLoading ? (
            <ProductGridSkeleton count={FILTER_LIMIT} />
          ) : productsQuery.isError ? (
            <EmptyState
              title="Hubo un error al buscar"
              description="No pudimos conectar con el servicio de productos. Inténtalo nuevamente."
            />
          ) : productsQuery.data && productsQuery.data.items.length > 0 ? (
            <>
              <ProductGrid products={productsQuery.data.items} />
              {totalPages > 1 ? (
                <Pagination current={page} totalPages={totalPages} onPageChange={goToPage} />
              ) : null}
            </>
          ) : (
            <EmptyState
              title="Sin resultados"
              description={
                q
                  ? `No encontramos productos para “${q}”. Probá con otros términos o quitá los filtros.`
                  : "No hay productos que coincidan con los filtros seleccionados."
              }
              actionLabel="Limpiar filtros"
              actionHref="/search"
            />
          )}
        </div>
      </div>

      <Dialog open={mobileFiltersOpen} onOpenChange={setMobileFiltersOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Filtros</DialogTitle>
            <DialogDescription>Filtrá los resultados por categoría, marca y precio.</DialogDescription>
          </DialogHeader>
          <SearchFilters categories={categoriesQuery.data} />
        </DialogContent>
      </Dialog>
    </div>
  );
}

function DebouncedSearchBar({ initialValue }: { initialValue: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [inputValue, setInputValue] = useState(initialValue);
  const deferred = useDeferredValue(inputValue);
  const search = searchParams.toString();

  useEffect(() => {
    if (deferred === initialValue) return;
    const timeout = setTimeout(() => {
      const params = new URLSearchParams(search);
      const term = deferred.trim();
      if (term) params.set("q", term);
      else params.delete("q");
      params.set("page", "1");
      router.push(`/search?${params.toString()}`);
    }, 400);
    return () => clearTimeout(timeout);
  }, [deferred, initialValue, router, search]);

  return (
    <div className="relative flex w-full max-w-md items-center">
      <Search className="pointer-events-none absolute left-3 h-4 w-4 text-muted-foreground" />
      <Input
        value={inputValue}
        onChange={(event) => setInputValue(event.target.value)}
        placeholder="Buscar dentro de los resultados…"
        className="pl-9"
        aria-label="Buscar productos"
      />
    </div>
  );
}

function Pagination({
  current,
  totalPages,
  onPageChange,
}: {
  current: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  const pages = useMemo(() => {
    const set = new Set<number>([1, totalPages, current, current - 1, current + 1]);
    return Array.from(set)
      .filter((page) => page >= 1 && page <= totalPages)
      .sort((a, b) => a - b);
  }, [current, totalPages]);

  return (
    <nav className="mt-8 flex flex-wrap items-center justify-center gap-1" aria-label="Paginación">
      <Button
        variant="outline"
        size="sm"
        disabled={current <= 1}
        onClick={() => onPageChange(current - 1)}
      >
        Anterior
      </Button>
      {pages.map((page, index) => {
        const prev = pages[index - 1];
        const isGap = prev !== undefined && page - prev > 1;
        return (
          <span key={page} className="flex items-center gap-1">
            {isGap ? <span className="px-1 text-muted-foreground">…</span> : null}
            <Button
              variant={page === current ? "default" : "outline"}
              size="sm"
              onClick={() => onPageChange(page)}
              className="min-w-9"
            >
              {page}
            </Button>
          </span>
        );
      })}
      <Button
        variant="outline"
        size="sm"
        disabled={current >= totalPages}
        onClick={() => onPageChange(current + 1)}
      >
        Siguiente
      </Button>
    </nav>
  );
}

function parseInteger(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function SearchPageSkeleton() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
      <Skeleton className="mb-6 h-8 w-64" />
      <div className="grid gap-8 lg:grid-cols-[240px_1fr]">
        <Skeleton className="hidden h-96 rounded-xl lg:block" />
        <div>
          <Skeleton className="mb-4 h-5 w-40" />
          <ProductGridSkeleton count={FILTER_LIMIT} />
        </div>
      </div>
    </div>
  );
}
