import type { ProductRead, ProductSearchParams, ProductSearchResult } from "@/types/product";
import { getWithRetry } from "@/lib/api/http";

function toQueryString(params: ProductSearchParams): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    searchParams.set(key, String(value));
  }
  const query = searchParams.toString();
  return query ? `?${query}` : "";
}

export async function searchProducts(params: ProductSearchParams): Promise<ProductSearchResult> {
  const res = await getWithRetry(`/api/v1/products${toQueryString(params)}`);
  if (!res.ok) {
    throw new Error(`Error al buscar productos (${res.status})`);
  }
  return res.json();
}

export async function fetchProduct(productId: number | string): Promise<ProductRead> {
  const res = await getWithRetry(`/api/v1/products/${productId}`);
  if (!res.ok) {
    if (res.status === 404) {
      throw new Error("Producto no encontrado");
    }
    throw new Error(`Error al cargar el producto (${res.status})`);
  }
  return res.json();
}
