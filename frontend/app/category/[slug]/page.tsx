"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { createElement, Suspense, useState } from "react";
import { ArrowRight, SlidersHorizontal } from "lucide-react";

import { CategoryBreadcrumbs } from "@/components/category/category-breadcrumbs";
import {
  CategoryFilters,
  buildSpecFilterQueries,
  parseFilters,
  serializeFilters,
  type FilterState,
} from "@/components/category/category-filters";
import { SortSelect } from "@/components/category/sort-select";
import { EmptyState } from "@/components/product/empty-state";
import { ProductGrid, ProductGridSkeleton } from "@/components/product/product-grid";
import { useCompare } from "@/components/product/compare-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Pagination } from "@/components/ui/pagination";
import { Skeleton } from "@/components/ui/skeleton";
import { categoryDescription, categoryIcon } from "@/lib/catalog-meta";
import { useCategories, useCategoryBySlug, useCategoryFacets, useProducts } from "@/hooks/use-catalog";
import { findCategoryChain, isLeafCategory, type CategoryRead } from "@/types/category";

const PAGE_SIZE = 12;

export default function CategoryPage() {
  return (
    <Suspense fallback={<CategoryPageSkeleton />}>
      <CategoryContent />
    </Suspense>
  );
}

function CategoryContent() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);

  const categoriesQuery = useCategories();
  const categoryQuery = useCategoryBySlug(slug);
  const compare = useCompare();

  const category = categoryQuery.data;
  const isGroup = category ? !isLeafCategory(category) : false;

  const facetsQuery = useCategoryFacets(category && !isGroup ? slug : undefined);
  const chain = category ? (findCategoryChain(categoriesQuery.data ?? [], slug) ?? [category]) : null;

  const sort = searchParams.get("sort") ?? "price_asc";
  const pageRaw = Number(searchParams.get("page") ?? "1");
  const page = Number.isFinite(pageRaw) && pageRaw > 0 ? pageRaw : 1;
  const filters = parseFilters(searchParams.get("f"));

  const productsQuery = useProducts({
    category: slug,
    sort,
    brand: filters.brand.length > 0 ? filters.brand.join(",") : undefined,
    min_price_clp: filters.minPrice ?? undefined,
    max_price_clp: filters.maxPrice ?? undefined,
    ...buildSpecFilterQueries(filters),
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });

  function updateUrl(updates: { sort?: string | null; page?: number | null; filters?: FilterState | null }) {
    const params = new URLSearchParams(searchParams.toString());
    if (updates.sort !== undefined) {
      if (updates.sort) params.set("sort", updates.sort);
      else params.delete("sort");
    }
    if (updates.page !== undefined) {
      if (updates.page) params.set("page", String(updates.page));
      else params.delete("page");
    }
    if (updates.filters !== undefined) {
      const serialized = updates.filters ? serializeFilters(updates.filters) : undefined;
      if (serialized) params.set("f", serialized);
      else params.delete("f");
    }
    router.replace(`/category/${encodeURIComponent(slug)}?${params.toString()}`, { scroll: false });
  }

  if (categoryQuery.isLoading || !category) return <CategoryPageSkeleton />;

  if (categoryQuery.isError) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6">
        <EmptyState
          title="Categoría no encontrada"
          description="La categoría que buscas no existe o aún no está publicada."
          actionLabel="Volver al inicio"
          actionHref="/"
        />
      </div>
    );
  }

  const chainItems =
    chain && chain.length > 1
      ? chain.slice(0, -1).map((node) => ({ label: node.name, href: `/category/${node.slug}` }))
      : [];

  const header = <CategoryHeader category={category} />;

  if (isGroup) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
        <CategoryBreadcrumbs items={chainItems} />
        {header}
        {category.children.length > 0 ? (
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {category.children.map((child) => {
              const ChildIcon = categoryIcon(child);
              return (
                <Link
                  key={child.id}
                  href={`/category/${child.slug}`}
                  className="group flex items-center gap-3 rounded-xl border bg-card p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
                >
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <ChildIcon className="size-5" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">{child.name}</span>
                    <span className="block text-xs text-muted-foreground">
                      {child.children.length} {child.children.length === 1 ? "categoría" : "categorías"}
                      {child.total_products > 0 ? ` · ${child.total_products} producto${child.total_products === 1 ? "" : "s"}` : ""}
                    </span>
                  </span>
                  <ArrowRight className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-1 group-hover:text-primary" />
                </Link>
              );
            })}
          </div>
        ) : (
          <div className="mt-6">
            <EmptyState
              title="Aún no hay subcategorías"
              description="Esta categoría se está preparando. Vuelve pronto."
              actionLabel="Ver todas las categorías"
              actionHref="/"
            />
          </div>
        )}
      </div>
    );
  }

  const total = productsQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const items = productsQuery.data?.items ?? [];
  const activeFilterCount = filterCount(filters);

  const filtersPanel = (
    <CategoryFilters
      facets={facetsQuery.data}
      value={filters}
      onChange={(next) => updateUrl({ filters: next, page: null })}
      onClear={() => updateUrl({ filters: null, page: null })}
      isLoading={facetsQuery.isLoading}
    />
  );

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
      <CategoryBreadcrumbs items={chainItems} />
      {header}

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {productsQuery.isLoading ? "Buscando productos…" : `${total} producto${total === 1 ? "" : "s"}`}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          {activeFilterCount > 0 ? (
            <Button variant="ghost" size="sm" onClick={() => updateUrl({ filters: null, page: null })}>
              Limpiar filtros
            </Button>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            className="gap-2 lg:hidden"
            onClick={() => setMobileFiltersOpen(true)}
          >
            <SlidersHorizontal className="h-4 w-4" />
            Filtros
            {activeFilterCount > 0 ? <Badge className="min-w-5 justify-center">{activeFilterCount}</Badge> : null}
          </Button>
          <SortSelect value={sort} onChange={(value) => updateUrl({ sort: value, page: null })} />
        </div>
      </div>

      <div className="mt-6 grid gap-8 lg:grid-cols-[260px_1fr]">
        <aside className="hidden lg:block">
          <div className="sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto rounded-xl border bg-card p-4">
            <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
              <SlidersHorizontal className="h-4 w-4" />
              Filtros
            </h2>
            {filtersPanel}
          </div>
        </aside>

        <div>
          {productsQuery.isLoading ? (
            <ProductGridSkeleton count={8} />
          ) : productsQuery.isError ? (
            <EmptyState title="Hubo un error" description="No pudimos cargar los productos. Inténtalo nuevamente." />
          ) : items.length > 0 ? (
            <>
              <ProductGrid
                products={items}
                compare={{ selectedIds: compare.selected, onToggle: compare.toggle }}
              />
              {totalPages > 1 ? (
                <Pagination current={page} totalPages={totalPages} onPageChange={(next) => updateUrl({ page: next })} />
              ) : null}
            </>
          ) : (
            <EmptyState
              title="Sin resultados"
              description="No hay productos que coincidan con los filtros seleccionados."
              actionLabel="Limpiar filtros"
              actionHref={`/category/${encodeURIComponent(slug)}`}
            />
          )}
        </div>
      </div>

      <Dialog open={mobileFiltersOpen} onOpenChange={setMobileFiltersOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Filtros</DialogTitle>
            <DialogDescription>Filtrá por marca, precio y características de {category.name}.</DialogDescription>
          </DialogHeader>
          {filtersPanel}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CategoryHeader({ category }: { category: CategoryRead }) {
  return (
    <header className="mt-4">
      <h1 className="flex items-center gap-3 text-2xl font-bold tracking-tight sm:text-3xl">
        <span className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
          {createElement(categoryIcon(category), { className: "size-6" })}
        </span>
        {category.name}
      </h1>
      <p className="mt-2 max-w-2xl text-muted-foreground">{categoryDescription(category)}</p>
    </header>
  );
}

function filterCount(filters: FilterState): number {
  return (
    filters.brand.length +
    (filters.minPrice !== null ? 1 : 0) +
    (filters.maxPrice !== null ? 1 : 0) +
    Object.values(filters.spec).reduce((sum, values) => sum + values.length, 0) +
    Object.values(filters.ranges).filter((range) => range.min !== null || range.max !== null).length
  );
}

function CategoryPageSkeleton() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
      <Skeleton className="h-4 w-64" />
      <div className="mt-4 flex items-center gap-3">
        <Skeleton className="size-11 rounded-xl" />
        <Skeleton className="h-8 w-56" />
      </div>
      <Skeleton className="mt-3 h-4 w-full max-w-2xl" />
      <Skeleton className="mt-2 h-4 w-2/3 max-w-xl" />
      <div className="mt-6">
        <ProductGridSkeleton count={8} />
      </div>
    </div>
  );
}