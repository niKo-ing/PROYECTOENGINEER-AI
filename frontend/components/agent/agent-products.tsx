"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { ProductImage } from "@/components/product/product-image";
import type { AgentProductCard } from "@/lib/api/agent";
import { formatCLP } from "@/lib/utils";

/** Tarjetas de los productos que el agente consultó en este turno (sale de sus herramientas, no del modelo). */
export function AgentProducts({ products }: { products: AgentProductCard[] }) {
  if (products.length === 0) return null;
  return (
    <div className="mt-3" aria-label="Productos consultados">
      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">Productos consultados</p>
      <ul className="flex snap-x gap-3 overflow-x-auto pb-2">
        {products.map((product) => {
          const price = product.lowest_price ?? product.price_clp;
          return (
            <li key={product.id} className="w-40 shrink-0 snap-start">
              <Link
                href={`/product/${product.id}`}
                className="group flex h-full flex-col overflow-hidden rounded-xl border bg-card transition duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md"
              >
                <ProductImage src={product.image_url} alt={product.name} className="aspect-square" zoomOnHover />
                <div className="flex flex-1 flex-col gap-1 p-2.5">
                  {product.brand ? <span className="text-[11px] font-medium uppercase text-muted-foreground">{product.brand}</span> : null}
                  <span className="line-clamp-2 text-xs font-medium leading-4">{product.name}</span>
                  <span className="mt-auto pt-1 text-sm font-semibold">{price ? formatCLP(price) : "Sin precio"}</span>
                  {product.lowest_price_store ? <span className="truncate text-[11px] text-muted-foreground">en {product.lowest_price_store}</span> : null}
                  <span className="flex items-center gap-1 text-[11px] font-medium text-primary">
                    Ver ficha <ArrowRight className="size-3" aria-hidden="true" />
                  </span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
