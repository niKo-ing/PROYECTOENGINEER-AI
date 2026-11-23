"use client";

import { useEffect, useRef, useState } from "react";

import type { Span } from "@/lib/api/pc";
import { cn } from "@/lib/utils";

export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms >= 1000) return `${(ms / 1000).toLocaleString("es-CL", { maximumFractionDigits: 1 })} s`;
  return `${Math.round(ms).toLocaleString("es-CL")} ms`;
}

const H = 200;
const PAD = { top: 12, right: 64, bottom: 24, left: 44 };

function niceMax(value: number): number {
  if (value <= 0) return 1;
  const exp = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((m) => m * exp >= value) ?? 10;
  return step * exp;
}

function ticks(max: number): number[] {
  return [0, max / 2, max];
}

type Hover = { index: number; x: number } | null;

/** Ancho real del contenedor: el SVG se dibuja a 1 unidad = 1 px y el texto no se achica en el celular. */
function useWidth(fallback = 640) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.round(entry.contentRect.width))));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Cada cuántas etiquetas del eje x se muestra una, para que no choquen (~90 px por etiqueta). */
const labelEvery = (count: number, innerW: number) => Math.max(1, Math.ceil(count / Math.max(2, Math.floor(innerW / 90))));

function Tooltip({ hover, width, children }: { hover: Hover; width: number; children: React.ReactNode }) {
  if (!hover) return null;
  const left = `${(hover.x / width) * 100}%`;
  return (
    <div
      className="pointer-events-none absolute top-0 z-10 min-w-36 -translate-x-1/2 rounded-md border bg-popover px-3 py-2 text-xs shadow-md"
      style={{ left }}
      role="status"
    >
      {children}
    </div>
  );
}

/** Columnas de una sola serie (p. ej. ejecuciones por hora). */
export function ColumnChart({ labels, values, valueLabel, details, ariaLabel }: { labels: string[]; values: number[]; valueLabel: (v: number) => string; details?: string[]; ariaLabel: string }) {
  const [hover, setHover] = useState<Hover>(null);
  const [box, W] = useWidth();
  const max = niceMax(Math.max(0, ...values));
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const band = innerW / Math.max(1, values.length);
  const barW = Math.min(24, Math.max(2, band - 2));
  const y = (v: number) => PAD.top + innerH - (v / max) * innerH;
  const every = labelEvery(values.length, innerW);

  return (
    <div ref={box} className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label={ariaLabel} onPointerLeave={() => setHover(null)}>
        {ticks(max).map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--viz-grid)" strokeWidth={1} />
            <text x={PAD.left - 6} y={y(t) + 4} textAnchor="end" className="fill-muted-foreground text-[10px] tabular-nums">
              {t === 0 ? "0" : valueLabel(t)}
            </text>
          </g>
        ))}
        {values.map((v, i) => {
          const x = PAD.left + i * band + (band - barW) / 2;
          const top = y(v);
          const h = PAD.top + innerH - top;
          const r = Math.min(4, h, barW / 2);
          const path = h > 0 ? `M${x},${top + h} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${top + h} Z` : "";
          return (
            <g key={i}>
              {path ? <path d={path} fill="var(--viz-1)" opacity={hover && hover.index !== i ? 0.55 : 1} /> : null}
              <rect
                x={PAD.left + i * band}
                y={PAD.top}
                width={band}
                height={innerH}
                fill="transparent"
                tabIndex={0}
                aria-label={`${labels[i]}: ${valueLabel(v)}${details?.[i] ? `, ${details[i]}` : ""}`}
                onPointerEnter={() => setHover({ index: i, x: x + barW / 2 })}
                onFocus={() => setHover({ index: i, x: x + barW / 2 })}
                onBlur={() => setHover(null)}
                className="outline-none focus-visible:stroke-[var(--ring)]"
              />
              {i % every === 0 ? (
                <text x={x + barW / 2} y={H - 6} textAnchor="middle" className="fill-muted-foreground text-[10px]">
                  {labels[i]}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      <Tooltip hover={hover} width={W}>
        {hover ? (
          <>
            <p className="text-sm font-semibold tabular-nums">{valueLabel(values[hover.index])}</p>
            <p className="text-muted-foreground">{labels[hover.index]}</p>
            {details?.[hover.index] ? <p className="text-muted-foreground">{details[hover.index]}</p> : null}
          </>
        ) : null}
      </Tooltip>
    </div>
  );
}

type Series = { name: string; color: string; values: (number | null)[] };

/** Líneas con cursor vertical que sigue al puntero; leyenda y etiqueta al final de cada línea. */
export function LineChart({ labels, series, valueLabel, ariaLabel }: { labels: string[]; series: Series[]; valueLabel: (v: number) => string; ariaLabel: string }) {
  const [hover, setHover] = useState<Hover>(null);
  const [box, W] = useWidth();
  const svgRef = useRef<SVGSVGElement>(null);
  const all = series.flatMap((s) => s.values.filter((v): v is number => v !== null));
  const max = niceMax(Math.max(0, ...all));
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (labels.length <= 1 ? innerW / 2 : (i / (labels.length - 1)) * innerW);
  const y = (v: number) => PAD.top + innerH - (v / max) * innerH;
  const every = labelEvery(labels.length, innerW);

  function onMove(event: React.PointerEvent<SVGSVGElement>) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || labels.length === 0) return;
    const px = ((event.clientX - rect.left) / rect.width) * W;
    const index = Math.max(0, Math.min(labels.length - 1, Math.round(((px - PAD.left) / innerW) * (labels.length - 1))));
    setHover({ index, x: x(index) });
  }

  const ends = series
    .map((s) => {
      const last = [...s.values].reverse().findIndex((v) => v !== null);
      const index = last === -1 ? -1 : s.values.length - 1 - last;
      return { s, index, value: index >= 0 ? (s.values[index] as number) : null };
    })
    .filter((e) => e.value !== null);
  // Etiquetas al final sin choques: si quedan a menos de 12 px, se separan.
  const endY = ends.map((e) => y(e.value as number)).map((v, i, arr) => (i > 0 && Math.abs(v - arr[i - 1]) < 12 ? arr[i - 1] + (v >= arr[i - 1] ? 12 : -12) : v));

  return (
    <div ref={box}>
      <ul className="mb-2 flex flex-wrap gap-4 text-xs text-muted-foreground" aria-label="Leyenda">
        {series.map((s) => (
          <li key={s.name} className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 rounded" style={{ background: s.color }} aria-hidden="true" />
            {s.name}
          </li>
        ))}
      </ul>
      <div className="relative">
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="h-auto w-full touch-none" role="img" aria-label={ariaLabel} onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
          {ticks(max).map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--viz-grid)" strokeWidth={1} />
              <text x={PAD.left - 6} y={y(t) + 4} textAnchor="end" className="fill-muted-foreground text-[10px] tabular-nums">
                {t === 0 ? "0" : valueLabel(t)}
              </text>
            </g>
          ))}
          {labels.map((label, i) =>
            i % every === 0 ? (
              <text key={i} x={x(i)} y={H - 6} textAnchor="middle" className="fill-muted-foreground text-[10px]">
                {label}
              </text>
            ) : null,
          )}
          {hover ? <line x1={hover.x} x2={hover.x} y1={PAD.top} y2={PAD.top + innerH} stroke="currentColor" className="text-muted-foreground" strokeWidth={1} /> : null}
          {series.map((s) => {
            const d = s.values
              .map((v, i) => (v === null ? null : `${x(i)},${y(v)}`))
              .reduce<string[]>((acc, point, i, arr) => {
                if (point === null) return acc;
                acc.push(`${i === 0 || arr[i - 1] === null ? "M" : "L"}${point}`);
                return acc;
              }, [])
              .join(" ");
            return <path key={s.name} d={d} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />;
          })}
          {series.map((s) =>
            s.values.length === 1 && s.values[0] !== null ? <circle key={`${s.name}-dot`} cx={x(0)} cy={y(s.values[0])} r={4} fill={s.color} stroke="var(--background)" strokeWidth={2} /> : null,
          )}
          {hover
            ? series.map((s) => {
                const v = s.values[hover.index];
                return v === null ? null : <circle key={s.name} cx={hover.x} cy={y(v)} r={4} fill={s.color} stroke="var(--background)" strokeWidth={2} />;
              })
            : null}
          {ends.map((e, i) => (
            <text key={e.s.name} x={x(e.index) + 8} y={endY[i] + 4} className="fill-foreground text-[11px]">
              {e.s.name} {valueLabel(e.value as number)}
            </text>
          ))}
        </svg>
        <Tooltip hover={hover} width={W}>
          {hover ? (
            <>
              <p className="mb-1 text-muted-foreground">{labels[hover.index]}</p>
              {series.map((s) => (
                <p key={s.name} className="flex items-center gap-2">
                  <span className="inline-block h-0.5 w-3 rounded" style={{ background: s.color }} aria-hidden="true" />
                  <span className="font-semibold tabular-nums">{s.values[hover.index] === null ? "—" : valueLabel(s.values[hover.index] as number)}</span>
                  <span className="text-muted-foreground">{s.name}</span>
                </p>
              ))}
            </>
          ) : null}
        </Tooltip>
      </div>
    </div>
  );
}

const KIND_META: Record<Span["kind"], { label: string; color: string }> = {
  llm: { label: "Modelo (Gemini)", color: "var(--viz-1)" },
  tool: { label: "Herramienta", color: "var(--viz-2)" },
  stage: { label: "Etapa", color: "var(--viz-3)" },
};

/** Cascada de una ejecución: cada tramo en su momento y con su duración. Nombre y duración siempre visibles. */
export function Waterfall({ spans, total }: { spans: Span[]; total: number }) {
  const end = Math.max(total, ...spans.map((s) => s.start_ms + s.duration_ms), 1);
  const [hover, setHover] = useState<number | null>(null);
  return (
    <div>
      <ul className="mb-3 flex flex-wrap gap-4 text-xs text-muted-foreground" aria-label="Leyenda">
        {(Object.keys(KIND_META) as Span["kind"][]).map((kind) => (
          <li key={kind} className="flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-sm" style={{ background: KIND_META[kind].color }} aria-hidden="true" />
            {KIND_META[kind].label}
          </li>
        ))}
      </ul>
      <ol className="space-y-1.5">
        {spans.map((span, index) => {
          const left = (span.start_ms / end) * 100;
          const width = Math.max(0.6, (span.duration_ms / end) * 100);
          return (
            <li
              key={span.seq}
              tabIndex={0}
              onPointerEnter={() => setHover(index)}
              onPointerLeave={() => setHover(null)}
              onFocus={() => setHover(index)}
              onBlur={() => setHover(null)}
              className={cn("grid grid-cols-[150px_minmax(0,1fr)_72px] items-center gap-3 rounded px-1 text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring", hover === index && "bg-muted/60")}
              aria-label={`${KIND_META[span.kind].label} ${span.name}: empieza en ${formatMs(span.start_ms)} y dura ${formatMs(span.duration_ms)}${span.status !== "ok" ? `, ${span.status}` : ""}`}
            >
              <span className="truncate" title={span.name}>
                {span.name}
                {span.status !== "ok" ? <span className="ml-1 font-medium text-destructive">({span.status})</span> : null}
              </span>
              <span className="relative h-3 rounded-sm bg-muted/50">
                <span className="absolute inset-y-0 rounded-sm" style={{ left: `${left}%`, width: `${width}%`, background: KIND_META[span.kind].color }} />
              </span>
              <span className="text-right tabular-nums text-muted-foreground">{formatMs(span.duration_ms)}</span>
            </li>
          );
        })}
      </ol>
      {hover !== null ? (
        <p className="mt-2 text-xs text-muted-foreground" role="status">
          {spans[hover].name}: desde {formatMs(spans[hover].start_ms)}, dura {formatMs(spans[hover].duration_ms)}
          {spans[hover].input_tokens ? ` · ${spans[hover].input_tokens} tokens de entrada, ${spans[hover].output_tokens ?? 0} de salida` : ""}
        </p>
      ) : null}
    </div>
  );
}
