import type { PriceHistoryRead, StoreOfferRead } from "@/types/offer";
import { getWithRetry } from "@/lib/api/http";

export async function fetchOffers(productId: number | string): Promise<StoreOfferRead[]> {
  const res = await getWithRetry(`/api/v1/products/${productId}/offers`);
  if (!res.ok) {
    throw new Error(`Error al cargar ofertas (${res.status})`);
  }
  return res.json();
}

export async function fetchPriceHistory(productId: number | string): Promise<PriceHistoryRead[]> {
  const res = await getWithRetry(`/api/v1/products/${productId}/price-history`);
  if (!res.ok) {
    throw new Error(`Error al cargar historial de precios (${res.status})`);
  }
  return res.json();
}
