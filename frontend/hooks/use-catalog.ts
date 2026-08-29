"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchCategories } from "@/lib/api/categories";
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


