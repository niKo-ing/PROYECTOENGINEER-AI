"use client";

import Link from "next/link";
import { ArrowRight, LayoutGrid, Sparkles } from "lucide-react";

import { CategoryList } from "@/components/product/category-list";
import { EmptyState } from "@/components/product/empty-state";
import { HomeSearchBar } from "@/components/product/home-search-bar";
import { ProductGrid, ProductGridSkeleton } from "@/components/product/product-grid";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCategories, useProducts } from "@/hooks/use-catalog";

const FEATURED_LIMIT = 8;

export default function HomePage() {
  const categoriesQuery = useCategories();
  const featuredQuery = useProducts({ limit: FEATURED_LIMIT });

  const featured = featuredQuery.data?.items ?? [];
  const featuredError = featuredQuery.isError;

  return (
    <div>
      <section className="border-b bg-gradient-to-b from-muted/60 to-background">
        <div className="mx-auto max-w-7xl px-4 py-14 text-center sm:px-6 sm:py-20">
          <span className="mb-4 inline-flex items-center gap-1.5 rounded-full border bg-background px-3 py-1 text-xs font-medium text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            Compara precios entre tiendas en un solo lugar
          </span>
          <h1 className="mx-auto max-w-3xl text-3xl font-bold tracking-tight sm:text-5xl">
            Encuentra el <span className="text-primary">mejor precio</span> antes de comprar
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-muted-foreground sm:text-lg">
            Busca productos, compara ofertas entre tiendas y sigue el historial de precios para decidir cuándo comprar.
          </p>
          <div className="mt-8">
            <HomeSearchBar />
          </div>
        </div>
      </section>

      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
        <section className="mb-12">
          <SectionHeading
            icon={<LayoutGrid className="h-5 w-5" />}
            title="Explora por categoría"
          />
          {categoriesQuery.isLoading ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {Array.from({ length: 8 }).map((_, index) => (
                <Skeleton key={index} className="h-12 rounded-xl" />
              ))}
            </div>
          ) : categoriesQuery.isError ? (
            <EmptyState title="No pudimos cargar las categorías" description="Inténtalo nuevamente en unos momentos." />
          ) : categoriesQuery.data && categoriesQuery.data.length > 0 ? (
            <CategoryList categories={categoriesQuery.data} />
          ) : (
            <EmptyState title="Aún no hay categorías" description="Cuando haya datos disponibles aparecerán aquí." />
          )}
        </section>

        <section>
          <SectionHeading
            icon={<Sparkles className="h-5 w-5" />}
            title="Productos destacados"
            action={
              <Button variant="ghost" size="sm" asChild className="gap-1 text-primary">
                <Link href="/search">
                  Ver todos
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
            }
          />
          {featuredQuery.isLoading ? (
            <ProductGridSkeleton count={FEATURED_LIMIT} />
          ) : featuredError ? (
            <EmptyState title="No pudimos cargar los productos" description="Revisa que el backend esté disponible e inténtalo de nuevo." />
          ) : featured.length > 0 ? (
            <ProductGrid products={featured} />
          ) : (
            <EmptyState title="Aún no hay productos disponibles" description="Cuando haya productos publicados aparecerán aquí." />
          )}
        </section>
      </div>
    </div>
  );
}

function SectionHeading({
  icon,
  title,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex items-center justify-between gap-2">
      <h2 className="flex items-center gap-2 text-lg font-semibold sm:text-xl">
        <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
          {icon}
        </span>
        {title}
      </h2>
      {action}
    </div>
  );
}
