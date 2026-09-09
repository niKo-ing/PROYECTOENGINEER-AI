"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Award, CalendarClock, ChevronDown, MessageSquare, RefreshCw, Store, WifiOff } from "lucide-react";

import { OffersList } from "@/components/product/offers-list";
import { PriceHistoryChart } from "@/components/product/price-history-chart";
import { ProductGallery } from "@/components/product/product-gallery";
import { ProductFeatureSummary, SpecSheet } from "@/components/product/product-specs";
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
    <div className="mx-auto w-full max-w-[92rem] px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <BackLink />

      {/* Encabezado del producto */}
      <div className="mb-8 grid gap-8 xl:grid-cols-[minmax(0,1fr)_360px] xl:gap-14 2xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="grid min-w-0 gap-8 lg:grid-cols-[minmax(22rem,27rem)_minmax(0,1fr)] xl:gap-10">
          <ProductGallery
            images={galleryImages}
            alt={product.name}
            className="mx-auto w-full max-w-sm lg:max-w-none lg:self-start"
          />

          <div className="min-w-0 self-start pt-1">
            <div className="mb-4 flex flex-wrap items-center gap-2">
              {product.brand ? <Badge variant="secondary">{product.brand}</Badge> : null}
              {product.category ? <Badge variant="outline">{product.category}</Badge> : null}
              {product.rating ? (
                <span className="flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-sm font-medium text-amber-700">
                  ★ {Number(product.rating).toFixed(1)}
                </span>
              ) : null}
            </div>
            <h1 className="max-w-[34rem] text-lg font-bold leading-snug tracking-tight text-foreground sm:text-xl lg:text-2xl">{product.name}</h1>

            <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted-foreground">
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

            <ProductFeatureSummary
              name={product.name}
              brand={product.brand}
              category={product.category}
              canonicalSpecs={product.canonical_specs}
              specs={product.specs}
            />

          </div>
        </div>

        <Card className="h-fit shadow-sm xl:sticky xl:top-24 xl:ml-4">
          <CardContent className="p-6 sm:p-7">
            <p className="text-sm text-muted-foreground">Precio más bajo</p>
            {product.lowest_price !== null ? (
              <>
                <p className="mt-2 text-3xl font-bold tracking-tight">{formatCLP(product.lowest_price)}</p>
                {product.lowest_price_store ? (
                  <p className="mt-2 flex items-center gap-1.5 text-sm font-medium text-emerald-600">
                    <Award className="h-4 w-4" />
                    en {product.lowest_price_store}
                  </p>
                ) : null}
              </>
            ) : (
              <p className="mt-1 text-muted-foreground">Sin precios disponibles</p>
            )}
            <Separator className="my-5" />
            <p className="text-sm leading-6 text-muted-foreground">
              Compará las ofertas de las distintas tiendas para encontrar la mejor opción.
            </p>
            <Button asChild className="mt-6 w-full gap-2">
              <Link href={`/chat?product=${product.id}&name=${encodeURIComponent(product.name)}`}>
                <MessageSquare className="h-4 w-4" />
                Preguntá al asistente
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>

      <details className="group mb-8 rounded-xl border bg-card">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4">
          <span className="font-semibold tracking-tight text-foreground">Ver ficha técnica completa</span>
          <ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" aria-hidden="true" />
        </summary>
        <div className="border-t">
          <SpecSheet canonicalSpecs={product.canonical_specs} specs={product.specs} />
        </div>
      </details>

      <div className="rounded-xl border bg-card p-2 sm:p-3">
        <Tabs defaultValue="offers">
          <TabsList className="w-full justify-start sm:w-auto">
            <TabsTrigger value="offers" className="flex-1 sm:flex-none">
              Ofertas
            </TabsTrigger>
            <TabsTrigger value="history" className="flex-1 sm:flex-none">
              Historial de precios
            </TabsTrigger>
          </TabsList>
          <TabsContent value="offers" className="mt-5 px-1 pb-1 sm:px-2">
            <OffersList offers={offersQuery.data} isLoading={offersQuery.isLoading} isError={offersQuery.isError} />
          </TabsContent>
          <TabsContent value="history" className="px-1 pb-1 sm:px-2">
            <Card className="border-0 shadow-none">
              <CardHeader className="px-2 sm:px-3 sm:pt-5">
                <CardTitle className="text-base">Evolución del precio</CardTitle>
              </CardHeader>
              <CardContent className="px-2 sm:px-3">
                <PriceHistoryChart data={historyQuery.data ?? []} />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
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
    <div className="mx-auto w-full max-w-[92rem] px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <Skeleton className="h-4 w-24" />
      <div className="mt-6 grid gap-8 xl:grid-cols-[minmax(0,1fr)_360px] xl:gap-14 2xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="grid gap-8 lg:grid-cols-[minmax(22rem,27rem)_minmax(0,1fr)] xl:gap-10">
          <Skeleton className="aspect-[3/4] w-full rounded-xl" />
          <div className="space-y-4">
            <div className="flex gap-2">
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-6 w-24" />
            </div>
            <Skeleton className="h-12 w-3/4" />
            <Skeleton className="h-5 w-52" />
            <Skeleton className="h-28 w-full rounded-xl" />
          </div>
        </div>
        <Skeleton className="h-56 rounded-xl" />
      </div>
      <div className="mt-6 space-y-3">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-24 rounded-xl" />
        <Skeleton className="h-24 rounded-xl" />
      </div>
    </div>
  );
}
