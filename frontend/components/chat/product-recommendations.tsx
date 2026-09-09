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

const SPEC_LABELS: Record<string, string> = {
  pcie_slot_list: "PCIe",
  m2_slot_list: "M.2",
  rear_ports: "Puertos",
  fan_header_list: "Ventilacion",
  cpu_power_connector_types: "CPU power",
  motherboard_power_connector: "Power",
  supported_cpu_generations: "CPU",
  supported_memory_speeds: "Memoria",
  overclock_memory_speeds: "Memoria OC",
  dimensions: "Dimensiones",
};

function getSpecPreview(product: ProductRead) {
  const canonicalItems = (product.canonical_specs?.sections ?? [])
    .flatMap((section) => section.items)
    .filter((item) => item.value && item.value !== "No especificado")
    .slice(0, 4)
    .map((item) => ({
      label: SPEC_LABELS[item.key] ?? item.label,
      value: item.value,
    }));

  if (canonicalItems.length > 0) return canonicalItems;

  return (product.specs?.highlights ?? [])
    .slice(0, 4)
    .map((highlight) => {
      const [label, ...value] = highlight.split(":");
      return value.length > 0
        ? { label: label.trim(), value: value.join(":").trim() }
        : { label: "Detalle", value: highlight };
    });
}

function useRecommendationSwap(products: ProductRead[], messageId: string | undefined) {
  const [displayed, setDisplayed] = useState<MappedProducts>(() => ({ key: "empty-0", products: [] }));
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const key = messageId ?? `products-${products.length}`;
    if (key === displayed.key) return;
    if (products.length === 0) {
      const clear = window.setTimeout(() => {
        setDisplayed({ key, products: [] });
        setVisible(true);
      }, 0);
      return () => window.clearTimeout(clear);
    }
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
  const specPreview = getSpecPreview(product);

  return (
    <Link
      href={`/product/${product.id}`}
      className="animate-card-in group flex min-w-[18rem] max-w-[18rem] snap-start flex-col overflow-hidden rounded-2xl border bg-card shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md sm:min-w-[22rem] sm:max-w-[22rem] lg:min-w-0 lg:max-w-none lg:flex-row"
      style={{ animationDelay: `${index * 55}ms` }}
    >
      <ProductImage
        src={product.image_url}
        alt={product.name}
        className="aspect-[4/3] w-full border-b lg:aspect-[3/4] lg:w-36 lg:shrink-0 lg:border-b-0 lg:border-r xl:w-40"
      />
      <div className="flex min-w-0 flex-1 flex-col p-4">
        <h3 className="line-clamp-2 text-base font-semibold leading-6 text-foreground">{product.name}</h3>
        <p className="mt-2 text-xl font-semibold tracking-tight text-foreground">
          {formatCLP(product.lowest_price)}
        </p>
        <p className="mt-1 line-clamp-2 text-sm leading-5 text-muted-foreground">
          {product.lowest_price_store ?? "Sin tienda"}
          {product.offer_count > 0
            ? ` · ${product.offer_count} oferta${product.offer_count === 1 ? "" : "s"}`
            : ""}
        </p>
        {hasRating ? <p className="mt-1.5 text-sm text-muted-foreground">★ {product.rating!.toFixed(1)}</p> : null}
        {specPreview.length > 0 ? (
          <dl className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
            {specPreview.map((spec) => (
              <div key={`${spec.label}-${spec.value}`} className="min-w-0 rounded-lg bg-muted/60 px-2.5 py-2">
                <dt className="truncate text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{spec.label}</dt>
                <dd className="mt-0.5 line-clamp-2 text-xs font-semibold leading-4 text-foreground">{spec.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-primary">
          Ver producto
          <ArrowRight
            className="size-4 transition-transform duration-200 group-hover:translate-x-0.5"
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
      <aside className="hidden min-h-0 min-w-0 lg:flex">
        <div
          className={cn(
            "flex min-h-0 flex-1 flex-col bg-card lg:rounded-2xl lg:border",
            "transition-opacity duration-200",
            swap.visible ? "opacity-100" : "opacity-0"
          )}
          aria-label="Productos recomendados"
        >
          <PanelHeader count={list.length} />
          {list.length > 0 ? (
            <div className="flex-1 overflow-y-auto overscroll-contain p-4">
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
        <details className="min-h-0 min-w-0 overflow-y-auto max-h-[35dvh] border-t bg-card lg:hidden">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium">Productos recomendados ({list.length})</summary>
          <div
            className={cn("rounded-3xl border bg-card p-4 shadow-sm transition-opacity duration-200", swap.visible ? "opacity-100" : "opacity-0")}
          >
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              Artículos
            </p>
            <p className="mb-3 mt-0.5 text-sm font-medium text-foreground">Recomendados para ti</p>
            <div className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-2 lg:hidden">
              {list.map((product, index) => (
                <ProductCard key={product.id} product={product} index={index} />
              ))}
            </div>
          </div>
        </details>
      ) : null}
    </>
  );
}
