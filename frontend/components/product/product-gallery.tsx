"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight, ImageOff, ZoomIn } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

type ProductGalleryProps = {
  images: string[];
  alt: string;
  className?: string;
};

export function ProductGallery({ images, alt, className }: ProductGalleryProps) {
  const urls = images.length > 0 ? images : [];
  const [activeIndex, setActiveIndex] = useState(0);
  const [zoomed, setZoomed] = useState(false);
  const [zoomOrigin, setZoomOrigin] = useState({ x: 50, y: 50 });
  const [lightboxOpen, setLightboxOpen] = useState(false);

  const active = urls[activeIndex] ?? null;
  const hasGallery = urls.length > 1;

  if (urls.length === 0) {
    return (
      <div className={cn("relative aspect-[3/4] overflow-hidden rounded-xl bg-muted", className)}>
        <div
          className="flex h-full w-full items-center justify-center text-muted-foreground"
          aria-hidden="true"
        >
          <ImageOff className="h-10 w-10" />
        </div>
      </div>
    );
  }

  function handleMove(event: React.MouseEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * 100;
    const y = ((event.clientY - rect.top) / rect.height) * 100;
    setZoomOrigin({ x, y });
    setZoomed(true);
  }

  function previous() {
    setActiveIndex((i) => (i - 1 + urls.length) % urls.length);
  }

  function next() {
    setActiveIndex((i) => (i + 1) % urls.length);
  }

  return (
    <div className={cn("w-full", className)}>
      <div
        className="group relative aspect-[3/4] cursor-zoom-in overflow-hidden rounded-xl bg-muted"
        onMouseMove={handleMove}
        onMouseLeave={() => setZoomed(false)}
        onClick={() => setLightboxOpen(true)}
      >
        <img
          src={active!}
          alt={`${alt} - imagen ${activeIndex + 1}`}
          loading="eager"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setActiveIndex((i) => (i + 1) % urls.length)}
          className={cn(
            "h-full w-full object-contain p-2 transition-transform duration-200 will-change-transform",
            zoomed ? "scale-[2.2]" : "scale-100"
          )}
          style={{ transformOrigin: `${zoomOrigin.x}% ${zoomOrigin.y}%` }}
        />
        <span
          className="pointer-events-none absolute bottom-3 right-3 flex items-center gap-1 rounded-full bg-foreground/80 px-2.5 py-1 text-xs font-medium text-background opacity-0 transition-opacity duration-200 group-hover:opacity-100"
          aria-hidden="true"
        >
          <ZoomIn className="h-3.5 w-3.5" />
          Ampliar
        </span>
      </div>

      {hasGallery ? (
        <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
          {urls.map((url, index) => (
            <button
              key={url}
              type="button"
              onClick={() => setActiveIndex(index)}
              aria-label={`Ver imagen ${index + 1}`}
              aria-pressed={index === activeIndex}
              className={cn(
                "relative aspect-[3/4] w-16 shrink-0 overflow-hidden rounded-md border-2 bg-muted transition-all duration-200",
                index === activeIndex
                  ? "border-primary ring-1 ring-primary"
                  : "border-transparent opacity-60 hover:opacity-100"
              )}
            >
              <img
                src={url}
                alt={`${alt} - miniatura ${index + 1}`}
                loading="lazy"
                decoding="async"
                referrerPolicy="no-referrer"
                className="h-full w-full object-contain p-0.5"
              />
            </button>
          ))}
        </div>
      ) : null}

      <Dialog open={lightboxOpen} onOpenChange={setLightboxOpen}>
        <DialogContent
          className="w-[min(92vw,1100px)] max-w-none border-0 bg-black/90 p-0 text-white sm:rounded-xl"
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") previous();
            if (event.key === "ArrowRight") next();
          }}
        >
          <DialogTitle className="sr-only">
            {alt} - imagen {activeIndex + 1} de {urls.length}
          </DialogTitle>
          <DialogDescription className="sr-only">
            Galería del producto {alt}
          </DialogDescription>

          <div className="relative flex min-h-[50vh] items-center justify-center p-4 sm:p-8">
            <img
              src={active!}
              alt={`${alt} - vista ampliada ${activeIndex + 1}`}
              referrerPolicy="no-referrer"
              className="max-h-[75vh] w-auto max-w-full rounded-lg object-contain"
            />
          </div>

          {urls.length > 1 ? (
            <>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-black/40 text-white hover:bg-black/60 hover:text-white sm:left-4"
                onClick={previous}
                aria-label="Imagen anterior"
              >
                <ChevronLeft className="h-6 w-6" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-black/40 text-white hover:bg-black/60 hover:text-white sm:right-4"
                onClick={next}
                aria-label="Imagen siguiente"
              >
                <ChevronRight className="h-6 w-6" />
              </Button>
            </>
          ) : null}

          <div className="flex items-center justify-center gap-2 pb-4">
            {urls.map((url, index) => (
              <button
                key={url}
                type="button"
                onClick={() => setActiveIndex(index)}
                aria-label={`Ver imagen ${index + 1}`}
                className={cn(
                  "aspect-[3/4] w-10 overflow-hidden rounded border-2 transition-colors",
                  index === activeIndex ? "border-white" : "border-transparent opacity-50 hover:opacity-100"
                )}
              >
                <img
                  src={url}
                  alt=""
                  loading="lazy"
                  referrerPolicy="no-referrer"
                  className="h-full w-full object-contain p-0.5"
                />
              </button>
            ))}
          </div>

          <span className="pointer-events-none absolute bottom-3 right-4 text-xs text-white/80">
            {activeIndex + 1} / {urls.length}
          </span>
        </DialogContent>
      </Dialog>
    </div>
  );
}