"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Award, CalendarClock, ChevronDown, MessageSquare, RefreshCw, Sparkles, Store, WifiOff } from "lucide-react";

import { OffersList } from "@/components/product/offers-list";
import { PriceHistoryChart } from "@/components/product/price-history-chart";
import { ProductGallery } from "@/components/product/product-gallery";
import { SpecHighlights, SpecSheet } from "@/components/product/product-specs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useOffers, usePriceHistory, useProduct } from "@/hooks/use-catalog";
import { formatCLP } from "@/lib/utils";

export default function ProductPage() {
  const params = useParams<{ id: string }>();
  const productId = params?.id;

  const productQuery = useProduct(productId);
  const offersQuery = useOffers(productId);
  const historyQuery = usePriceHistory(productId);

  if (productQuery.isLoading) {
    return <ProductDetailSkeleton />;
  }

  const isNotFound =
    !productId ||
    !/^\d+$/.test(productId) ||
    (productQuery.isError ? (productQuery.error as Error | null)?.message === "Producto no encontrado" : !productQuery.data);

  if (productQuery.isError || !productQuery.data) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-16 sm:px-6">
        <BackLink />
        {isNotFound ? (
          <div className="rounded-xl border border-dashed bg-muted/30 px-6 py-16 text-center">
            <h1 className="text-lg font-semibold">No encontramos este producto</h1>
            <p className="mt-2 text-sm text-muted-foreground">El producto podría no existir o haber sido eliminado.</p>
            <Button asChild variant="outline" className="mt-4">
              <Link href="/search">Volver a buscar</Link>
            </Button>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed bg-muted/30 px-6 py-16 text-center">
            <WifiOff className="mx-auto size-8 text-muted-foreground" aria-hidden="true" />
            <h1 className="mt-4 text-lg font-semibold">No pudimos cargar este producto</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Hubo un problema de conexión con el servicio de productos. Revisá tu conexión e intentá nuevamente.
            </p>
            <Button variant="outline" className="mt-4 gap-2" onClick={() => void productQuery.refetch()}>
              <RefreshCw className="h-4 w-4" />
              Reintentar
            </Button>
          </div>
        )}
      </div>
    );
  }

  const product = productQuery.data;
  const galleryImages = product.images.length > 0 ? product.images : [product.image_url].filter(Boolean) as string[];

  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
      <BackLink />

      {/* Encabezado del producto */}
      <div className="mb-6 grid gap-6 lg:grid-cols-[1fr_320px]">
        <div>
          <ProductGallery
            images={galleryImages}
            alt={product.name}
            className="mx-auto mb-6 max-w-sm sm:max-w-md lg:max-w-lg"
          />
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {product.brand ? <Badge variant="secondary">{product.brand}</Badge> : null}
            {product.category ? <Badge variant="outline">{product.category}</Badge> : null}
            {product.rating ? (
              <span className="flex items-center gap-1 text-sm font-medium text-amber-600">
                ★ {Number(product.rating).toFixed(1)}
              </span>
            ) : null}
          </div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{product.name}</h1>

          <div className="mt-4 flex flex-wrap gap-4 text-sm text-muted-foreground">
            {product.lowest_price_store ? (
              <span className="flex items-center gap-1.5">
                <Store className="h-4 w-4" />
                Disponible en {product.lowest_price_store}
              </span>
            ) : null}
            <span className="flex items-center gap-1.5">
              <CalendarClock className="h-4 w-4" />
              {product.offer_count} {product.offer_count === 1 ? "oferta" : "ofertas"}
            </span>
          </div>

          <SpecHighlights specs={product.specs} />

          {product.description_ai ? (
            <div className="mt-5 rounded-xl border bg-muted/40 p-4">
              <span className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">
                <Sparkles className="h-3.5 w-3.5" />
                Descripción generada con IA
              </span>
              <p className="text-sm leading-relaxed text-foreground sm:text-base">{product.description_ai}</p>
            </div>
          ) : null}

          <SpecSheet specs={product.specs} />

          {product.description ? (
            product.description.length > 300 ? (
              <details className="group mt-6 rounded-xl border px-4 py-3">
                <summary className="cursor-pointer list-none">
                  <span className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
                    <ChevronDown className="size-4 transition-transform group-open:rotate-180" aria-hidden="true" />
                    Descripción completa de la tienda
                  </span>
                </summary>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                  {product.description}
                </p>
              </details>
            ) : (
              <p className="mt-4 leading-relaxed text-muted-foreground">{product.description}</p>
            )
          ) : null}
        </div>

        <Card className="h-fit">
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">Precio más bajo</p>
            {product.lowest_price !== null ? (
              <>
                <p className="mt-1 text-3xl font-bold tracking-tight">{formatCLP(product.lowest_price)}</p>
                {product.lowest_price_store ? (
                  <p className="mt-1 flex items-center gap-1.5 text-sm text-emerald-600">
                    <Award className="h-4 w-4" />
                    en {product.lowest_price_store}
                  </p>
                ) : null}
              </>
            ) : (
              <p className="mt-1 text-muted-foreground">Sin precios disponibles</p>
            )}
            <Separator className="my-4" />
            <p className="text-xs text-muted-foreground">
              Compará las ofertas de las distintas tiendas para encontrar la mejor opción.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="rounded-xl border bg-card p-1">
        <Tabs defaultValue="offers">
          <TabsList className="w-full justify-start">
            <TabsTrigger value="offers" className="flex-1 sm:flex-none">
              Ofertas
            </TabsTrigger>
            <TabsTrigger value="history" className="flex-1 sm:flex-none">
              Historial de precios
            </TabsTrigger>
          </TabsList>
          <TabsContent value="offers" className="mt-4 px-2 pb-2 sm:px-3">
            <OffersList offers={offersQuery.data} isLoading={offersQuery.isLoading} isError={offersQuery.isError} />
          </TabsContent>
          <TabsContent value="history" className="px-2 pb-2 sm:px-3">
            <Card className="border-0 shadow-none">
              <CardHeader className="px-2 sm:px-3">
                <CardTitle className="text-base">Evolución del precio</CardTitle>
              </CardHeader>
              <CardContent>
                <PriceHistoryChart data={historyQuery.data ?? []} />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>

      <div className="mt-4 flex justify-center">
        <Button asChild className="w-full gap-2 sm:w-auto">
          <Link href={`/chat?product=${product.id}&name=${encodeURIComponent(product.name)}`}>
            <MessageSquare className="h-4 w-4" />
            Preguntá al asistente sobre este producto
          </Link>
        </Button>
      </div>
    </div>
  );
}

function BackLink() {
  const router = useRouter();
  return (
    <Button
      variant="ghost"
      size="sm"
      className="mb-4 gap-1 px-2 text-muted-foreground"
      onClick={() => router.back()}
    >
      <ArrowLeft className="h-4 w-4" />
      Volver
    </Button>
  );
}

function ProductDetailSkeleton() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
      <Skeleton className="h-4 w-24" />
      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          <div className="flex gap-2">
            <Skeleton className="h-6 w-20" />
            <Skeleton className="h-6 w-24" />
          </div>
          <Skeleton className="h-9 w-3/4" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-16 w-full" />
        </div>
        <Skeleton className="h-44 rounded-xl" />
      </div>
      <div className="mt-6 space-y-3">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-24 rounded-xl" />
        <Skeleton className="h-24 rounded-xl" />
      </div>
    </div>
  );
}
