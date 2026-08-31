import type { ProductRead } from "@/types/product";
import { ProductCard, type CompareControl } from "@/components/product/product-card";
import { Skeleton } from "@/components/ui/skeleton";

export function ProductCardSkeleton() {
  return (
    <div className="space-y-3 rounded-xl border bg-card p-4 shadow-sm">
      <Skeleton className="aspect-[3/4] w-full" />
      <div className="flex items-center justify-between">
        <Skeleton className="h-5 w-20" />
        <Skeleton className="h-4 w-8" />
      </div>
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-3 w-28" />
      <div className="pt-2">
        <Skeleton className="h-7 w-24" />
        <Skeleton className="mt-2 h-3 w-32" />
      </div>
      <Skeleton className="h-3 w-24" />
    </div>
  );
}

export interface ProductGridCompare {
  selectedIds: ReadonlySet<number>;
  onToggle: (id: number) => void;
}

export function ProductGrid({
  products,
  compare,
}: {
  products: ProductRead[];
  compare?: ProductGridCompare;
}) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {products.map((product) => {
        const control: CompareControl | undefined = compare
          ? { selected: compare.selectedIds.has(product.id), onToggle: () => compare.onToggle(product.id) }
          : undefined;
        return <ProductCard key={product.id} product={product} compare={control} />;
      })}
    </div>
  );
}

export function ProductGridSkeleton({ count = 8 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: count }).map((_, index) => (
        <ProductCardSkeleton key={index} />
      ))}
    </div>
  );
}
