import type { PriceHistoryRead, StoreOfferRead } from "@/types/offer";

export async function fetchOffers(productId: number | string): Promise<StoreOfferRead[]> {
  const res = await fetch(`/api/v1/products/${productId}/offers`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Error al cargar ofertas (${res.status})`);
  }
  return res.json();
}

export async function fetchPriceHistory(productId: number | string): Promise<PriceHistoryRead[]> {
  const res = await fetch(`/api/v1/products/${productId}/price-history`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Error al cargar historial de precios (${res.status})`);
  }
  return res.json();
}
