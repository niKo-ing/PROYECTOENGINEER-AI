import type { CategoryFacets } from "@/types/catalog";
import type { CategoryRead } from "@/types/category";

export async function fetchCategories(): Promise<CategoryRead[]> {
  const res = await fetch("/api/v1/categories", { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Error al cargar categorías (${res.status})`);
  }
  return res.json();
}

export async function fetchCategoryBySlug(slug: string): Promise<CategoryRead> {
  const res = await fetch(`/api/v1/categories/by-slug/${encodeURIComponent(slug)}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Error al cargar la categoría (${res.status})`);
  }
  return res.json();
}

export async function fetchFacets(params: { category?: string }): Promise<CategoryFacets> {
  const searchParams = new URLSearchParams();
  if (params.category) searchParams.set("category", params.category);
  const query = searchParams.toString();
  const res = await fetch(`/api/v1/products/facets${query ? `?${query}` : ""}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Error al cargar filtros (${res.status})`);
  }
  return res.json();
}