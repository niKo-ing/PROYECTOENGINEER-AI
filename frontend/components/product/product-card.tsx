import Link from "next/link";
import { ArrowRight, Package, Scale, Store } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ProductImage } from "@/components/product/product-image";
import { cn } from "@/lib/utils";
import { formatCLP } from "@/lib/utils";
import type { ProductRead } from "@/types/product";

export interface CompareControl {
  selected: boolean;
  onToggle: () => void;
}

export function ProductCard({ product, compare }: { product: ProductRead; compare?: CompareControl }) {
  const hasPrice = product.lowest_price !== null;
  const hasImages = product.images.length > 0;

  return (
    <div className="group relative h-full">
      <Link href={`/product/${product.id}`} className="block h-full focus-visible:outline-none">
        <Card className="flex h-full flex-col overflow-hidden border-muted bg-card transition-all duration-300 group-hover:-translate-y-0.5 group-hover:border-primary/40 group-hover:shadow-lg">
          <div className="relative">
            <ProductImage
              src={hasImages ? product.images[0] : product.image_url}
              alt={product.name}
              zoomOnHover
              className="w-full"
            />

            <div className="absolute inset-x-3 top-3 flex items-start justify-between gap-2">
              {product.brand ? (
                <Badge variant="secondary" className="max-w-[55%] truncate bg-background/90 shadow-sm backdrop-blur">
                  {product.brand}
                </Badge>
              ) : (
                <span />
              )}
              {product.rating ? (
                <span className="flex shrink-0 items-center gap-1 rounded-full bg-amber-500/95 px-2 py-0.5 text-xs font-semibold text-white shadow-sm">
                  ★ {Number(product.rating).toFixed(1)}
                </span>
              ) : null}
            </div>

            {product.offer_count > 1 ? (
              <span className="absolute bottom-3 left-3 rounded-full bg-foreground/85 px-2.5 py-1 text-xs font-medium text-background shadow-sm backdrop-blur">
                {product.offer_count} ofertas
              </span>
            ) : null}
          </div>

          <CardContent className="flex flex-1 flex-col gap-1.5 p-4">
            <h3 className="line-clamp-2 text-sm font-semibold text-foreground transition-colors group-hover:text-primary sm:text-base">
              {product.name}
            </h3>

            {product.category ? (
              <p className="text-xs text-muted-foreground">{product.category}</p>
            ) : null}

            <div className="mt-auto flex flex-col gap-2 pt-3">
              {hasPrice && product.lowest_price !== null ? (
                <div>
                  <p className="text-xl font-bold tracking-tight text-foreground sm:text-2xl">
                    {formatCLP(product.lowest_price)}
                  </p>
                  {product.lowest_price_store ? (
                    <p className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
                      <Store className="h-3 w-3" />
                      Mejor precio en {product.lowest_price_store}
                    </p>
                  ) : null}
                </div>
              ) : (
                <p className="text-base font-semibold text-muted-foreground">Sin precios disponibles</p>
              )}

              <div className="flex items-center justify-between border-t pt-3">
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Package className="h-3.5 w-3.5" />
                  {product.offer_count} {product.offer_count === 1 ? "oferta" : "ofertas"}
                </span>
                <span className="flex items-center gap-1 text-xs font-medium text-primary opacity-0 transition-opacity duration-200 group-hover:opacity-100">
                  Ver detalle
                  <ArrowRight className="h-3.5 w-3.5" />
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      </Link>

      {compare ? (
        <button
          type="button"
          aria-pressed={compare.selected}
          aria-label={compare.selected ? "Quitar de comparación" : "Agregar a comparación"}
          onClick={compare.onToggle}
          className={cn(
            "absolute bottom-3 right-3 z-10 flex size-8 items-center justify-center rounded-full border bg-background/90 text-muted-foreground shadow-sm backdrop-blur transition-all hover:scale-110",
            compare.selected
              ? "border-primary bg-primary text-primary-foreground"
              : "hover:border-primary/60 hover:text-primary"
          )}
        >
          <Scale className="size-4" />
        </button>
      ) : null}
    </div>
  );
}