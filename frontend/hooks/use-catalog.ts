"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchCategories, fetchCategoryBySlug, fetchFacets } from "@/lib/api/categories";
import { fetchProduct, searchProducts } from "@/lib/api/products";
import { fetchOffers, fetchPriceHistory } from "@/lib/api/offers";
import type { ProductSearchParams } from "@/types/product";

export function useCategories() {
  return useQuery({
    queryKey: ["categories"],
    queryFn: fetchCategories,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCategoryBySlug(slug: string) {
  return useQuery({
    queryKey: ["category", slug],
    queryFn: () => fetchCategoryBySlug(slug),
    enabled: Boolean(slug),
    staleTime: 5 * 60 * 1000,
  });
}

export function useCategoryFacets(category: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["facets", category],
    queryFn: () => fetchFacets({ category: category! }),
    enabled: enabled && Boolean(category),
    staleTime: 2 * 60 * 1000,
  });
}

export function useProducts(params: ProductSearchParams) {
  return useQuery({
    queryKey: ["products", params],
    queryFn: () => searchProducts(params),
    placeholderData: (previous) => previous,
    staleTime: 30 * 1000,
  });
}

export function useProduct(productId: string | undefined | null) {
  return useQuery({
    queryKey: ["product", productId],
    queryFn: () => fetchProduct(productId!),
    enabled: Boolean(productId),
    staleTime: 30 * 1000,
  });
}

export function useOffers(productId: string | number | undefined | null) {
  return useQuery({
    queryKey: ["offers", productId],
    queryFn: () => fetchOffers(productId!),
    enabled: Boolean(productId),
    staleTime: 30 * 1000,
  });
}

export function usePriceHistory(productId: string | number | undefined | null) {
  return useQuery({
    queryKey: ["priceHistory", productId],
    queryFn: () => fetchPriceHistory(productId!),
    enabled: Boolean(productId),
    staleTime: 30 * 1000,
  });
}


