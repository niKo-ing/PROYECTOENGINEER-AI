import type { Metadata } from "next";
import "./globals.css";

import { SiteFooter } from "@/components/layout/site-footer";
import { SiteHeader } from "@/components/layout/site-header";
import { CompareBar } from "@/components/product/compare-bar";
import { CompareProvider } from "@/components/product/compare-provider";
import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "SoloTodo — Comparador de precios",
  description: "Compara precios de productos entre tiendas, revisa ofertas y sigue su historial de precios.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body className="min-h-screen antialiased">
        <CompareProvider>
          <Providers>
            <div className="flex min-h-screen flex-col">
              <SiteHeader />
              <main className="flex-1">{children}</main>
              <SiteFooter />
              <CompareBar />
            </div>
          </Providers>
        </CompareProvider>
      </body>
    </html>
  );
}
