import Link from "next/link";
import { ChevronRight, Home } from "lucide-react";

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

export function CategoryBreadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav aria-label="Migas de pan" className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
      <Link href="/" className="flex items-center gap-1.5 rounded-sm transition-colors hover:text-foreground">
        <Home className="h-3.5 w-3.5" />
        Inicio
      </Link>
      {items.map((item, index) => (
        <span key={`${item.href ?? item.label}-${index}`} className="flex items-center gap-1">
          <ChevronRight className="h-3.5 w-3.5 opacity-60" aria-hidden="true" />
          {item.href ? (
            <Link href={item.href} className="rounded-sm transition-colors hover:text-foreground">
              {item.label}
            </Link>
          ) : (
            <span className="font-medium text-foreground" aria-current="page">
              {item.label}
            </span>
          )}
        </span>
      ))}
    </nav>
  );
}