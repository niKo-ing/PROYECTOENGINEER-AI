import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SoloTodo AI",
  description: "Plataforma de descubrimiento y comparación de productos.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
