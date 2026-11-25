"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, Bot, Cpu, LayoutGrid, Sparkles, Wrench } from "lucide-react";

import { EmptyState } from "@/components/product/empty-state";
import { HomeSearchBar } from "@/components/product/home-search-bar";
import { ProductGrid, ProductGridSkeleton } from "@/components/product/product-grid";
import { useCompare } from "@/components/product/compare-provider";
import { CategoryExplorer, CategoryExplorerSkeleton } from "@/components/category/category-explorer";
import { Button } from "@/components/ui/button";
import { useCategories, useProducts } from "@/hooks/use-catalog";
import { mainGroups } from "@/types/category";

const FEATURED_LIMIT = 8;

export default function HomePage() {
  const categoriesQuery = useCategories();
  const featuredQuery = useProducts({ limit: FEATURED_LIMIT });
  const compare = useCompare();

  const featured = featuredQuery.data?.items ?? [];
  const featuredError = featuredQuery.isError;
  const groups = mainGroups(categoriesQuery.data ?? []);

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
        <section className="mb-12" aria-labelledby="armar-titulo">
          <SectionHeading icon={<Cpu className="h-5 w-5" />} title="Arma tu PC sin errores" id="armar-titulo" />
          <div className="grid gap-4 md:grid-cols-3">
            {[
              { href: "/armar/asistente", icon: Bot, title: "Que la IA te lo arme", text: "Cuéntale para qué lo quieres y cuánto tienes. Te pregunta lo que falte y arma un PC compatible." },
              { href: "/armar", icon: Wrench, title: "Ármalo pieza por pieza", text: "Cada opción te dice si calza: socket, tipo de memoria, medidas del gabinete y watts de la fuente." },
              { href: "/guias", icon: BookOpen, title: "Aprende qué es compatible", text: "Guías cortas sobre sockets, DDR4 y DDR5, fuentes, gabinetes y refrigeración." },
            ].map(({ href, icon: Icon, title, text }) => (
              <Link key={href} href={href} className="group flex flex-col gap-2 rounded-xl border bg-card p-5 transition-colors hover:border-primary/50 hover:bg-muted/30">
                <Icon className="h-6 w-6 text-primary" />
                <h3 className="font-semibold">{title}</h3>
                <p className="text-sm text-muted-foreground">{text}</p>
                <span className="mt-auto inline-flex items-center gap-1 pt-2 text-sm font-medium text-primary">
                  Empezar <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                </span>
              </Link>
            ))}
          </div>
        </section>

        <section className="mb-12">
          <SectionHeading
            icon={<LayoutGrid className="h-5 w-5" />}
            title="Explora por categoría"
          />
          {categoriesQuery.isLoading ? (
            <CategoryExplorerSkeleton count={6} />
          ) : categoriesQuery.isError ? (
            <EmptyState title="No pudimos cargar las categorías" description="Inténtalo nuevamente en unos momentos." />
          ) : groups.length > 0 ? (
            <CategoryExplorer groups={groups} />
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
            <ProductGrid
              products={featured}
              compare={{ selectedIds: compare.selected, onToggle: compare.toggle }}
            />
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
  id,
}: {
  icon: React.ReactNode;
  title: string;
  action?: React.ReactNode;
  id?: string;
}) {
  return (
    <div className="mb-4 flex items-center justify-between gap-2">
      <h2 id={id} className="flex items-center gap-2 text-lg font-semibold sm:text-xl">
        <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
          {icon}
        </span>
        {title}
      </h2>
      {action}
    </div>
  );
}
