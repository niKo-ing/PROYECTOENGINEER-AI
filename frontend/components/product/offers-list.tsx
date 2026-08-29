"use client";

import { CheckCircle2, ExternalLink, Store, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/product/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import {
  availabilityLabel,
  discountPercent,
  formatCLP,
  formatDateTime,
} from "@/lib/utils";
import type { StoreOfferRead } from "@/types/offer";

export function OffersList({ offers, isLoading, isError }: { offers: StoreOfferRead[] | undefined; isLoading: boolean; isError: boolean }) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-24 rounded-xl" />
        ))}
      </div>
    );
  }

  if (isError) {
    return <EmptyState title="No pudimos cargar las ofertas" description="Inténtalo nuevamente en unos momentos." />;
  }

  if (!offers || offers.length === 0) {
    return <EmptyState title="No hay ofertas disponibles" description="Este producto aún no tiene ofertas en ninguna tienda." />;
  }

  const lowest = Math.min(...offers.map((offer) => offer.price));

  return (
    <ul className="space-y-3">
      {offers.map((offer) => {
        const isLowest = offer.price === lowest;
        const discount = discountPercent(offer.original_price, offer.price);
        const available = availabilityLabel(offer.stock_status, offer.availability);
        const isAvailable = available === "Disponible";

        return (
          <li
            key={offer.id}
            className="relative rounded-xl border bg-card p-4 sm:p-5 transition-shadow hover:shadow-md"
          >
            {isLowest ? (
              <Badge className="absolute -top-2.5 right-4">Mejor precio</Badge>
            ) : null}

            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex items-start gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground">
                  <Store className="h-5 w-5" />
                </span>
                <div>
                  <p className="font-semibold">{offer.store.name}</p>
                  <p className="text-xs text-muted-foreground">{offer.store.domain}</p>
                  {offer.seller_name ? (
                    <p className="mt-0.5 text-xs text-muted-foreground">Vendido por {offer.seller_name}</p>
                  ) : null}
                </div>
              </div>

              <div className="flex items-center gap-3 sm:flex-col sm:items-end">
                <div className="text-right">
                  {offer.original_price && offer.original_price > offer.price ? (
                    <p className="text-xs text-muted-foreground line-through">{formatCLP(offer.original_price)}</p>
                  ) : null}
                  <p className="text-xl font-bold tracking-tight">
                    {formatCLP(offer.price)}
                  </p>
                </div>
                {discount ? <Badge variant="success">-{discount}%</Badge> : null}
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
              <span className={`flex items-center gap-1 font-medium ${isAvailable ? "text-emerald-600" : "text-rose-600"}`}>
                {isAvailable ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
                {available}
              </span>
              {offer.payment_condition ? <span>{offer.payment_condition}</span> : null}
              {offer.currency ? <span>Moneda: {offer.currency}</span> : null}
            </div>

            <div className="mt-3 flex items-center justify-between border-t pt-3">
              <p className="text-xs text-muted-foreground">
                Verificado {formatDateTime(offer.last_checked_at)}
              </p>
              <a
                href={offer.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
              >
                Ir a la tienda
                <ExternalLink className="h-4 w-4" />
              </a>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
