import Link from "next/link";

import { flattenCategories } from "@/types/category";
import type { CategoryRead } from "@/types/category";

export function CategoryList({ categories }: { categories: CategoryRead[] }) {
  const flat = flattenCategories(categories);

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {flat.map((category) => (
        <Link
          key={category.id}
          href={`/search?category=${encodeURIComponent(category.name)}`}
          className="group flex items-center rounded-xl border bg-card px-4 py-3 text-sm font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-accent"
        >
          <span className="line-clamp-1 group-hover:text-primary">{category.name}</span>
        </Link>
      ))}
    </div>
  );
}
