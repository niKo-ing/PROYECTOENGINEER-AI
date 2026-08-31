"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";
import { Scale, X } from "lucide-react";

import { EmptyState } from "@/components/product/empty-state";
import { ProductGridSkeleton } from "@/components/product/product-grid";
import { ProductImage } from "@/components/product/product-image";
import { useCompare } from "@/components/product/compare-provider";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useProducts } from "@/hooks/use-catalog";
import { formatCLP } from "@/lib/utils";
import type { CanonicalSpecItem, ProductRead } from "@/types/product";

export default function ComparePage() {
  return (
    <Suspense fallback={<ComparePageSkeleton />}>
      <CompareContent />
    </Suspense>
  );
}

function CompareContent() {
  const searchParams = useSearchParams();
  const compare = useCompare();

  const urlIds = parseIds(searchParams.get("ids"));
  const ids = urlIds.length > 0 ? urlIds : compare.ids;

  const productsQuery = useProducts(ids.length > 0 ? { ids: ids.join(",") } : {});
  const products = useMemo(
    () =>
      (productsQuery.data?.items ?? []).filter((product) => ids.includes(product.id)).sort((a, b) => {
        const indexA = ids.indexOf(a.id);
        const indexB = ids.indexOf(b.id);
        return (indexA === -1 ? Number.MAX_SAFE_INTEGER : indexA) - (indexB === -1 ? Number.MAX_SAFE_INTEGER : indexB);
      }),
    [productsQuery.data, ids]
  );

  const rows = useMemo(() => buildComparisonRows(products), [products]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-3 text-2xl font-bold tracking-tight sm:text-3xl">
          <span className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Scale className="size-6" />
          </span>
          Comparar productos
        </h1>
        {ids.length > 0 ? (
          <div className="flex items-center gap-2">
            <p className="text-sm text-muted-foreground">
              {products.length} de {ids.length} productos cargados
            </p>
            <Button variant="outline" size="sm" onClick={compare.clear}>
              Vaciar comparación
            </Button>
          </div>
        ) : null}
      </div>

      {productsQuery.isLoading ? (
        <CompareGridSkeleton count={ids.length || 1} />
      ) : productsQuery.isError ? (
        <EmptyState title="Hubo un error" description="No pudimos cargar los productos a comparar." />
      ) : products.length === 0 ? (
        <div className="py-10">
          <EmptyState
            title="No hay productos para comparar"
            description="Usá el botón de comparar en cada producto para armar tu lista (hasta 4)."
            actionLabel="Explorar productos"
            actionHref="/search"
          />
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border bg-card">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 w-48 bg-card p-3 text-left align-bottom font-semibold text-muted-foreground">
                  Producto
                </th>
                {products.map((product) => (
                  <th key={product.id} className="w-56 min-w-56 p-3 align-top">
                    <span className="relative block">
                      <button
                        type="button"
                        aria-label={`Quitar ${product.name} de la comparación`}
                        onClick={() => compare.remove(product.id)}
                        className="absolute -right-1 -top-1 z-10 flex size-6 items-center justify-center rounded-full border bg-background text-muted-foreground shadow-sm transition-colors hover:border-destructive/50 hover:text-destructive"
                      >
                        <X className="size-3.5" />
                      </button>
                      <Link
                        href={`/product/${product.id}`}
                        className="block text-left transition-colors hover:text-primary focus-visible:outline-none"
                      >
                        <ProductImage
                          src={product.images[0] ?? product.image_url}
                          alt={product.name}
                          className="w-full rounded-lg border"
                        />
                        <span className="mt-2 block text-xs">{product.brand ?? "Sin marca"}</span>
                        <span className="mt-1 block line-clamp-2 font-medium">{product.name}</span>
                      </Link>
                      {product.lowest_price !== null ? (
                        <div className="mt-2 rounded-lg bg-primary/10 px-2 py-1.5 text-center">
                          <p className="text-lg font-bold text-primary">{formatCLP(product.lowest_price)}</p>
                          {product.lowest_price_store ? (
                            <p className="text-[11px] text-muted-foreground">{product.lowest_price_store}</p>
                          ) : null}
                        </div>
                      ) : (
                        <p className="mt-2 text-xs text-muted-foreground">Sin precios</p>
                      )}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) =>
                row.type === "section" ? (
                  <tr key={row.title}>
                    <td colSpan={products.length + 1} className="bg-muted/50 p-3 font-semibold text-muted-foreground">
                      {row.title}
                    </td>
                  </tr>
                ) : (
                  <tr key={row.key} className="border-t">
                    <th className="sticky left-0 z-10 bg-card p-3 text-left align-top font-medium text-muted-foreground">
                      {row.label}
                    </th>
                    {row.values.map((cell, index) => (
                      <td key={products[index]?.id ?? index} className="p-3 align-top">
                        {cell ? <span className="text-foreground">{cell}</span> : <span className="text-muted-foreground">—</span>}
                      </td>
                    ))}
                  </tr>
                )
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

type ComparisonRow =
  | { type: "section"; title: string; key: string }
  | { type: "value"; key: string; label: string; values: (string | null)[] };

function buildComparisonRows(products: ProductRead[]): ComparisonRow[] {
  const rows: ComparisonRow[] = [];
  const keyBySection = new Map<string, Map<string, CanonicalSpecItem>>();

  for (const product of products) {
    for (const section of product.canonical_specs?.sections ?? []) {
      let sectionMap = keyBySection.get(section.title);
      if (!sectionMap) {
        sectionMap = new Map();
        keyBySection.set(section.title, sectionMap);
      }
      for (const item of section.items) {
        if (!sectionMap.has(item.key)) sectionMap.set(item.key, item);
      }
    }
  }

  for (const [title, sectionItems] of keyBySection) {
    rows.push({ type: "section", title, key: `section-${title}` });
    for (const item of sectionItems.values()) {
      const values = products.map((product) => lookupSpec(product, item.key));
      if (values.every((value) => !value)) continue;
      rows.push({ type: "value", key: item.key, label: item.label ?? item.key, values });
    }
  }
  return rows;
}

function lookupSpec(product: ProductRead, key: string): string | null {
  for (const section of product.canonical_specs?.sections ?? []) {
    for (const item of section.items) {
      if (item.key === key) {
        return item.value ? `${item.value}${item.unit ? ` ${item.unit}` : ""}` : null;
      }
    }
  }
  return null;
}

function parseIds(payload: string | null): number[] {
  if (!payload) return [];
  const parsed = payload
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isInteger(item) && item > 0)
    .slice(0, 4);
  return Array.from(new Set(parsed));
}

function CompareGridSkeleton({ count }: { count: number }) {
  return (
    <div>
      <ProductGridSkeleton count={Math.min(4, count)} />
      <Skeleton className="mt-4 h-8 w-72" />
    </div>
  );
}

function ComparePageSkeleton() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
      <Skeleton className="mb-6 h-9 w-72" />
      <CompareGridSkeleton count={1} />
    </div>
  );
}