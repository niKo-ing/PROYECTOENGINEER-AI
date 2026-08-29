"use client";

import type { PriceHistoryRead } from "@/types/offer";
import { formatCLP, formatDate } from "@/lib/utils";

const WIDTH = 640;
const HEIGHT = 220;
const PAD_X = 16;
const PAD_Y = 24;

export function PriceHistoryChart({ data }: { data: PriceHistoryRead[] }) {
  if (data.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No hay historial de precios disponible.</p>;
  }

  const prices = data.map((item) => item.price);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const priceRange = maxPrice - minPrice || 1;

  const points = data.map((item, index) => {
    const x = PAD_X + (index / Math.max(1, data.length - 1)) * (WIDTH - PAD_X * 2);
    const y = HEIGHT - PAD_Y - ((item.price - minPrice) / priceRange) * (HEIGHT - PAD_Y * 2);
    return { x, y, item, index };
  });

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");

  const last = data[data.length - 1];
  const first = data[0];
  const changePercent =
    first.price !== last.price && first.price > 0
      ? ((last.price - first.price) / first.price) * 100
      : 0;

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          Rango observado: {formatDate(first.observed_at)} — {formatDate(last.observed_at)}
        </p>
        <span
          className={`text-sm font-semibold ${
            changePercent <= 0 ? "text-emerald-600" : "text-rose-600"
          }`}
        >
          {changePercent > 0 ? "+" : ""}
          {changePercent.toFixed(1)}% en el período
        </span>
      </div>
      <div className="overflow-x-auto rounded-xl border bg-muted/20">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-auto w-full min-w-[480px]"
          role="img"
          aria-label="Gráfico del historial de precios"
        >
          <defs>
            <linearGradient id="priceArea" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="oklch(0.488 0.243 264.376)" stopOpacity="0.25" />
              <stop offset="100%" stopColor="oklch(0.488 0.243 264.376)" stopOpacity="0" />
            </linearGradient>
          </defs>
          <line
            x1={PAD_X}
            y1={HEIGHT - PAD_Y}
            x2={WIDTH - PAD_X}
            y2={HEIGHT - PAD_Y}
            stroke="oklch(0.929 0.013 255.508)"
            strokeWidth={1}
          />
          <polygon
            points={`${points[0].x.toFixed(1)} ${HEIGHT - PAD_Y} ${path} ${points[points.length - 1].x.toFixed(1)} ${HEIGHT - PAD_Y}`}
            fill="url(#priceArea)"
          />
          <path d={path} fill="none" stroke="oklch(0.488 0.243 264.376)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {points.map((point) => (
            <g key={point.item.id}>
              <circle cx={point.x} cy={point.y} r={3.5} fill="oklch(1 0 0)" stroke="oklch(0.488 0.243 264.376)" strokeWidth={2}>
                <title>{`${formatDate(point.item.observed_at)}: ${formatCLP(point.item.price)}`}</title>
              </circle>
            </g>
          ))}
        </svg>
      </div>
      <div className="mt-1 flex justify-between px-1 text-xs text-muted-foreground">
        <span>{formatDate(first.observed_at)}</span>
        <span>{formatDate(last.observed_at)}</span>
      </div>
    </div>
  );
}
