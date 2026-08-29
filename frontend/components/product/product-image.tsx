"use client";

import { useState } from "react";
import { ImageOff } from "lucide-react";

import { cn } from "@/lib/utils";

type ProductImageProps = {
  src: string | null | undefined;
  alt: string;
  className?: string;
  zoomOnHover?: boolean;
};

export function ProductImage({ src, alt, className, zoomOnHover = false }: ProductImageProps) {
  const [error, setError] = useState(false);
  const showImage = Boolean(src) && !error;

  return (
    <div className={cn("relative aspect-[3/4] overflow-hidden bg-muted", className)}>
      {showImage ? (
        <img
          src={src!}
          alt={alt}
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setError(true)}
          className={cn(
            "h-full w-full object-contain p-2",
            zoomOnHover && "transition-transform duration-500 group-hover:scale-110"
          )}
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-muted-foreground" aria-hidden="true">
          <ImageOff className="h-8 w-8" />
        </div>
      )}
    </div>
  );
}