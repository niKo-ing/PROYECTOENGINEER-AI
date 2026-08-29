"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, PackageSearch } from "lucide-react";

import { ProductImage } from "@/components/product/product-image";
import { cn, formatCLP } from "@/lib/utils";
import type { ProductRead } from "@/types/product";

type MappedProducts = {
  key: string;
  products: ProductRead[];
};

function useRecommendationSwap(products: ProductRead[], messageId: string | undefined) {
  const [displayed, setDisplayed] = useState<MappedProducts>(() => ({ key: "empty-0", products: [] }));
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const key = messageId ?? `products-${products.length}`;
    if (key === displayed.key) return;
    const idle = window.setTimeout(() => setVisible(false), 0);
    const swap = window.setTimeout(() => {
      setDisplayed({ key, products });
      setVisible(true);
    }, 220);
    return () => {
      window.clearTimeout(idle);
      window.clearTimeout(swap);
    };
  }, [products, messageId, displayed.key]);

  return { products: displayed.products, visible, key: displayed.key };
}

function ProductCard({ product, index }: { product: ProductRead; index: number }) {
  const hasRating = product.rating !== null && product.rating !== undefined;
  return (
    <Link
      href={`/product/${product.id}`}
      className="animate-card-in group flex min-w-[15.5rem] max-w-[15.5rem] snap-start flex-col overflow-hidden rounded-2xl border bg-card shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md md:max-w-none"
      style={{ animationDelay: `${index * 55}ms` }}
    >
      <ProductImage
        src={product.image_url}
        alt={product.name}
        className="aspect-[4/3] w-full border-b"
      />
      <div className="flex flex-1 flex-col p-3.5">
        <h3 className="line-clamp-2 text-sm font-medium leading-5 text-foreground">{product.name}</h3>
        <p className="mt-2 text-lg font-semibold tracking-tight text-foreground">
          {formatCLP(product.lowest_price)}
        </p>
        <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
          {product.lowest_price_store ?? "Sin tienda"}
          {product.offer_count > 0
            ? ` · ${product.offer_count} oferta${product.offer_count === 1 ? "" : "s"}`
            : ""}
        </p>
        {hasRating ? <p className="mt-1 text-xs text-muted-foreground">★ {product.rating!.toFixed(1)}</p> : null}
        <span className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-primary">
          Ver producto
          <ArrowRight
            className="size-3.5 transition-transform duration-200 group-hover:translate-x-0.5"
            aria-hidden="true"
          />
        </span>
      </div>
    </Link>
  );
}

function PanelHeader({ count }: { count: number }) {
  return (
    <div className="border-b px-4 py-3.5 sm:px-5">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        Artículos
      </p>
      <p className="mt-0.5 text-sm font-medium text-foreground">Recomendados para ti</p>
      {count > 0 ? (
        <span className="mt-1 inline-flex rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
          {count} {count === 1 ? "producto" : "productos"}
        </span>
      ) : null}
    </div>
  );
}

function EmptyHint() {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed bg-muted/20 px-4 py-8 text-center">
      <PackageSearch className="size-6 text-muted-foreground/70" aria-hidden="true" />
      <p className="text-sm leading-5 text-muted-foreground">
        Los productos que te recomiende aparecerán aquí.
      </p>
    </div>
  );
}

export function ProductRecommendations({
  products,
  messageId,
}: {
  products: ProductRead[];
  messageId: string | undefined;
}) {
  const swap = useRecommendationSwap(products, messageId);
  const list = swap.products;

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden lg:block">
        <div
          className={cn(
            "flex h-[calc(100dvh-8.5rem)] min-h-[480px] flex-col rounded-3xl border bg-card shadow-sm",
            "transition-opacity duration-200",
            swap.visible ? "opacity-100" : "opacity-0"
          )}
          aria-label="Productos recomendados"
        >
          <PanelHeader count={list.length} />
          {list.length > 0 ? (
            <div className="flex-1 overflow-y-auto p-4">
              <div className="flex flex-col gap-3" key={swap.key}>
                {list.map((product, index) => (
                  <ProductCard key={product.id} product={product} index={index} />
                ))}
              </div>
            </div>
          ) : (
            <div className="p-4">
              <EmptyHint />
            </div>
          )}
        </div>
      </aside>

      {/* Mobile / tablet products below the chat */}
      {list.length > 0 ? (
        <section className="lg:hidden" aria-label="Productos recomendados">
          <div
            className={cn("rounded-3xl border bg-card p-4 shadow-sm transition-opacity duration-200", swap.visible ? "opacity-100" : "opacity-0")}
          >
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              Artículos
            </p>
            <p className="mb-3 mt-0.5 text-sm font-medium text-foreground">Recomendados para ti</p>
            <div className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-2 md:grid md:grid-cols-2 md:overflow-visible md:snap-none lg:hidden">
              {list.map((product, index) => (
                <ProductCard key={product.id} product={product} index={index} />
              ))}
            </div>
          </div>
        </section>
      ) : null}
    </>
  );
}