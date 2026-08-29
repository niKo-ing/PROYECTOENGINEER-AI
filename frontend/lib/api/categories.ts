import type { CategoryRead } from "@/types/category";

export async function fetchCategories(): Promise<CategoryRead[]> {
  const res = await fetch("/api/v1/categories", { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Error al cargar categorías (${res.status})`);
  }
  return res.json();
}
