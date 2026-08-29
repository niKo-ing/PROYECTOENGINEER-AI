import type { ProductRead, ProductSearchParams, ProductSearchResult } from "@/types/product";

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
  const res = await fetch(`/api/v1/products${toQueryString(params)}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Error al buscar productos (${res.status})`);
  }
  return res.json();
}

export async function fetchProduct(productId: number | string): Promise<ProductRead> {
  const res = await fetch(`/api/v1/products/${productId}`, { cache: "no-store" });
  if (!res.ok) {
    if (res.status === 404) {
      throw new Error("Producto no encontrado");
    }
    throw new Error(`Error al cargar el producto (${res.status})`);
  }
  return res.json();
}
