import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// crypto.randomUUID solo existe en contextos seguros (HTTPS o localhost): servido por HTTP, p. ej. detrás de un ALB
// sin certificado, no está. getRandomValues sí existe siempre, así que armamos el UUID v4 a mano.
export function newId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function formatCLP(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("es-CL", {
    style: "currency",
    currency: "CLP",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatCLPCompact(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const formatter = new Intl.NumberFormat("es-CL", {
    style: "currency",
    currency: "CLP",
    notation: "compact",
    maximumFractionDigits: 1,
  });
  return formatter.format(value);
}

export function discountPercent(original: number | null | undefined, current: number | undefined): number | null {
  if (!original || !current || original <= 0) return null;
  const discount = Math.round(((original - current) / original) * 100);
  return discount > 0 ? discount : null;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("es-CL", {
    day: "2-digit",
    month: "short",
    weekday: "short",
  }).format(new Date(iso));
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("es-CL", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

export function availabilityLabel(stockStatus: string | null | undefined, availability: boolean | undefined): string {
  if (availability === false || stockStatus === "out_of_stock" || stockStatus === "agotado") return "Agotado";
  if (stockStatus && stockStatus !== "in_stock" && stockStatus !== "disponible") {
    return stockStatus;
  }
  return "Disponible";
}
