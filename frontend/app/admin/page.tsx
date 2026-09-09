"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  Boxes,
  CheckCircle2,
  DatabaseZap,
  ExternalLink,
  Layers3,
  LayoutDashboard,
  Loader2,
  PackageSearch,
  RefreshCw,
  ShieldCheck,
  ShoppingCart,
  Store,
  Tags,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fetchAdminDashboard, fetchSpecReviewQueue, verifySpecValue, type VerifySpecValuePayload } from "@/lib/api/admin";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import type { AdminActivityItem, AdminDashboardResponse, AdminSpecValue } from "@/types/admin";

type AdminSection = "dashboard" | "products" | "categories" | "review" | "conflicts" | "stores" | "offers" | "ingestion" | "stats";

const SECTIONS: Array<{ id: AdminSection; label: string; description: string; Icon: typeof LayoutDashboard }> = [
  { id: "dashboard", label: "Dashboard", description: "Resumen operativo", Icon: LayoutDashboard },
  { id: "products", label: "Productos", description: "Catálogo maestro", Icon: PackageSearch },
  { id: "categories", label: "Categorías", description: "Taxonomía y specs", Icon: Layers3 },
  { id: "review", label: "Revisión", description: "Specs pendientes", Icon: ShieldCheck },
  { id: "conflicts", label: "Conflictos", description: "Datos divergentes", Icon: AlertTriangle },
  { id: "stores", label: "Tiendas", description: "Fuentes comerciales", Icon: Store },
  { id: "offers", label: "Ofertas", description: "Precios y stock", Icon: ShoppingCart },
  { id: "ingestion", label: "Ingesta", description: "Scrapers y sync", Icon: DatabaseZap },
  { id: "stats", label: "Estadísticas", description: "Calidad y cobertura", Icon: BarChart3 },
];

export default function AdminPage() {
  const [section, setSection] = useState<AdminSection>("dashboard");
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [manualToken, setManualToken] = useState("");
  const [dashboard, setDashboard] = useState<AdminDashboardResponse | null>(null);
  const [items, setItems] = useState<AdminSpecValue[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [verifyingId, setVerifyingId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadSession() {
      try {
        const { data } = await createSupabaseBrowserClient().auth.getSession();
        if (!cancelled) setAccessToken(data.session?.access_token ?? null);
      } catch {
        if (!cancelled) setAccessToken(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadSession();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    async function loadInitialData() {
      setLoading(true);
      setError("");
      try {
        const [dashboardResponse, reviewResponse] = await Promise.all([
          fetchAdminDashboard(accessToken!),
          fetchSpecReviewQueue(accessToken!),
        ]);
        if (!cancelled) {
          setDashboard(dashboardResponse);
          setItems(reviewResponse.items);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "No fue posible cargar administración.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadInitialData();
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  async function refresh(token = accessToken) {
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const [dashboardResponse, reviewResponse] = await Promise.all([
        fetchAdminDashboard(token),
        fetchSpecReviewQueue(token),
      ]);
      setDashboard(dashboardResponse);
      setItems(reviewResponse.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No fue posible actualizar administración.");
    } finally {
      setLoading(false);
    }
  }

  async function verifyItem(item: AdminSpecValue, payload?: VerifySpecValuePayload) {
    if (!accessToken) return;
    setVerifyingId(item.id);
    setError("");
    try {
      await verifySpecValue(accessToken, item.id, payload);
      await refresh(accessToken);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No fue posible verificar el dato.");
    } finally {
      setVerifyingId(null);
    }
  }

  const conflictItems = items.filter((item) => item.conflict_status === "pending");

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-primary">Administración</p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">Centro de gestión del catálogo</h1>
          <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
            Monitoreá cobertura, revisión humana, conflictos, productos, tiendas e ingesta desde una estructura preparada para escalar.
          </p>
        </div>
        <Button variant="outline" className="gap-2" onClick={() => void refresh()} disabled={!accessToken || loading}>
          <RefreshCw className="size-4" aria-hidden="true" />
          Actualizar
        </Button>
      </div>

      {!accessToken ? (
        <AuthRequiredCard manualToken={manualToken} setManualToken={setManualToken} setAccessToken={setAccessToken} />
      ) : (
        <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
          <AdminNav section={section} onChange={setSection} pending={items.length} conflicts={conflictItems.length} />
          <main className="min-w-0">
            {error ? <p className="mb-4 rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</p> : null}
            {loading ? <LoadingPanel /> : null}
            {!loading && section === "dashboard" ? <DashboardPanel dashboard={dashboard} reviewItems={items} /> : null}
            {!loading && section === "review" ? <ReviewPanel title="Specs pendientes" items={items} verifyingId={verifyingId} onVerify={verifyItem} /> : null}
            {!loading && section === "conflicts" ? <ReviewPanel title="Conflictos de especificaciones" items={conflictItems} verifyingId={verifyingId} onVerify={verifyItem} conflictsOnly /> : null}
            {!loading && !["dashboard", "review", "conflicts"].includes(section) ? <PlaceholderPanel section={section} /> : null}
          </main>
        </div>
      )}
    </div>
  );
}

function AuthRequiredCard({ manualToken, setManualToken, setAccessToken }: { manualToken: string; setManualToken: (value: string) => void; setAccessToken: (value: string | null) => void }) {
  return (
    <Card className="max-w-xl shadow-none">
      <CardHeader>
        <CardTitle className="text-base">Sesión requerida</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Iniciá sesión con Supabase o pegá temporalmente un access token para consultar endpoints protegidos.
        </p>
        <div className="flex gap-2">
          <Input value={manualToken} onChange={(event) => setManualToken(event.target.value)} placeholder="Bearer token" />
          <Button onClick={() => setAccessToken(manualToken.trim() || null)}>Usar</Button>
        </div>
        <Button asChild variant="outline">
          <Link href="/login">Ir a login</Link>
        </Button>
      </CardContent>
    </Card>
  );
}

function AdminNav({ section, onChange, pending, conflicts }: { section: AdminSection; onChange: (section: AdminSection) => void; pending: number; conflicts: number }) {
  return (
    <aside className="rounded-2xl border bg-card p-2 shadow-none lg:sticky lg:top-20 lg:h-fit">
      <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-1">
        {SECTIONS.map(({ id, label, description, Icon }) => {
          const active = section === id;
          const count = id === "review" ? pending : id === "conflicts" ? conflicts : null;
          return (
            <button
              key={id}
              type="button"
              onClick={() => onChange(id)}
              className={`rounded-xl px-3 py-3 text-left transition-colors ${active ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
            >
              <span className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-2 font-medium">
                  <Icon className="size-4" aria-hidden="true" />
                  {label}
                </span>
                {count !== null ? <Badge variant={active ? "secondary" : "outline"}>{count}</Badge> : null}
              </span>
              <span className={`mt-1 block text-xs ${active ? "text-primary-foreground/75" : "text-muted-foreground"}`}>{description}</span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}

function DashboardPanel({ dashboard, reviewItems }: { dashboard: AdminDashboardResponse | null; reviewItems: AdminSpecValue[] }) {
  const metrics = dashboard?.metrics;
  if (!metrics) return <EmptyPanel title="Sin métricas" description="No se pudo cargar el dashboard." />;

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Productos" value={metrics.products} Icon={Boxes} />
        <MetricCard label="Ofertas" value={metrics.offers} Icon={Tags} />
        <MetricCard label="Tiendas" value={metrics.stores} Icon={Store} />
        <MetricCard label="Specs pendientes" value={metrics.specs_pending} Icon={ShieldCheck} tone="warning" />
        <MetricCard label="Conflictos" value={metrics.conflicts} Icon={AlertTriangle} tone="danger" />
        <MetricCard label="Productos sin specs" value={metrics.products_without_specs} Icon={PackageSearch} tone="warning" />
        <MetricCard label="Productos sin verificar" value={metrics.products_unverified} Icon={AlertTriangle} tone="warning" />
        <MetricCard label="Productos verificados" value={metrics.products_verified} Icon={CheckCircle2} tone="success" />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
        <Card className="shadow-none">
          <CardHeader>
            <CardTitle className="text-base">Actividad reciente</CardTitle>
          </CardHeader>
          <CardContent>
            {dashboard.recent_activity.length ? (
              <div className="space-y-3">
                {dashboard.recent_activity.map((event) => <ActivityRow key={event.id} event={event} />)}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Todavía no hay actividad de especificaciones.</p>
            )}
          </CardContent>
        </Card>

        <Card className="shadow-none">
          <CardHeader>
            <CardTitle className="text-base">Trabajo pendiente</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {reviewItems.slice(0, 5).map((item) => (
              <div key={item.id} className="rounded-xl border bg-muted/20 p-3">
                <div className="flex items-center justify-between gap-2">
                  <Badge variant={item.conflict_status === "pending" ? "outline" : "secondary"} className={item.conflict_status === "pending" ? "border-amber-300 bg-amber-50 text-amber-700" : ""}>
                    {item.conflict_status === "pending" ? "Conflicto" : "Revisión"}
                  </Badge>
                  <span className="text-xs text-muted-foreground">{item.group}</span>
                </div>
                <p className="mt-2 line-clamp-1 text-sm font-medium">{item.product_name}</p>
                <p className="mt-1 text-xs text-muted-foreground">{item.label}: {item.value}</p>
              </div>
            ))}
            {!reviewItems.length ? <p className="text-sm text-muted-foreground">No hay especificaciones pendientes.</p> : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function MetricCard({ label, value, Icon, tone }: { label: string; value: number; Icon: typeof Boxes; tone?: "warning" | "success" | "danger" }) {
  const toneClass = tone === "warning" ? "text-amber-700" : tone === "success" ? "text-emerald-700" : tone === "danger" ? "text-destructive" : "text-foreground";
  return (
    <Card className="shadow-none">
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
          <Icon className={`size-4 ${toneClass}`} aria-hidden="true" />
        </div>
        <p className={`mt-2 text-3xl font-bold ${toneClass}`}>{value}</p>
      </CardContent>
    </Card>
  );
}

function ActivityRow({ event }: { event: AdminActivityItem }) {
  return (
    <div className="rounded-xl border bg-muted/20 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{activityLabel(event.action)}</Badge>
          <Badge variant="outline">{event.group}</Badge>
          <Badge variant="outline">{sourceLabel(event.source_type)}</Badge>
        </div>
        <time className="text-xs text-muted-foreground">{new Date(event.created_at).toLocaleString("es-CL")}</time>
      </div>
      <Link href={`/product/${event.product_id}`} className="mt-2 block text-sm font-semibold hover:text-primary hover:underline">
        {event.product_name}
      </Link>
      <p className="mt-1 text-xs text-muted-foreground">{event.label}</p>
      {event.changed_by ? <p className="mt-1 text-xs text-muted-foreground">Por {event.changed_by}</p> : null}
    </div>
  );
}

function ReviewPanel({ title, items, verifyingId, onVerify, conflictsOnly = false }: { title: string; items: AdminSpecValue[]; verifyingId: number | null; onVerify: (item: AdminSpecValue, payload?: VerifySpecValuePayload) => void; conflictsOnly?: boolean }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
          <p className="text-sm text-muted-foreground">
            {conflictsOnly ? "Datos entrantes divergentes que requieren resolución antes de verificar." : "Datos automáticos o en revisión listos para control humano."}
          </p>
        </div>
        <Badge variant="outline">{items.length} items</Badge>
      </div>
      {items.length ? (
        <div className="grid gap-4">
          {items.map((item) => <ReviewCard key={item.id} item={item} verifying={verifyingId === item.id} onVerify={(payload) => onVerify(item, payload)} />)}
        </div>
      ) : (
        <EmptyPanel title="Sin elementos" description={conflictsOnly ? "No hay conflictos pendientes." : "No hay especificaciones pendientes de revisión."} />
      )}
    </div>
  );
}

function ReviewCard({ item, verifying, onVerify }: { item: AdminSpecValue; verifying: boolean; onVerify: (payload?: VerifySpecValuePayload) => void }) {
  const hasConflict = item.conflict_status === "pending";
  const [editing, setEditing] = useState(false);
  const [draftValue, setDraftValue] = useState(item.raw_value || item.value);
  const [draftUnit, setDraftUnit] = useState(item.unit ?? "");
  const [draftSourceName, setDraftSourceName] = useState(item.source_name ?? "");
  const [draftSourceUrl, setDraftSourceUrl] = useState(item.source_url ?? "");
  const [draftNote, setDraftNote] = useState("");

  const hasCorrection = editing && (
    draftValue.trim() !== (item.raw_value || item.value).trim() ||
    draftUnit.trim() !== (item.unit ?? "") ||
    draftSourceName.trim() !== (item.source_name ?? "") ||
    draftSourceUrl.trim() !== (item.source_url ?? "")
  );

  function submitVerification() {
    const note = draftNote.trim() || (hasCorrection ? "Corregido y verificado desde /admin" : "Verificado desde /admin");
    if (!hasCorrection) {
      onVerify({ note });
      return;
    }
    onVerify(buildCorrectionPayload(item, draftValue, draftUnit, draftSourceName, draftSourceUrl, note));
  }

  return (
    <Card className="overflow-hidden shadow-none">
      <CardContent className="p-0">
        <div className="grid gap-0 xl:grid-cols-[1fr_280px]">
          <div className="p-4 sm:p-5">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Badge variant="secondary">{item.group}</Badge>
              <Badge variant={hasConflict ? "outline" : "secondary"} className={hasConflict ? "border-amber-300 bg-amber-50 text-amber-700" : ""}>
                {hasConflict ? "Conflicto" : statusLabel(item.verification_status)}
              </Badge>
              <Badge variant="outline">{sourceLabel(item.source_type)}</Badge>
            </div>
            <Link href={`/product/${item.product_id}`} className="font-semibold hover:text-primary hover:underline">
              {item.product_name}
            </Link>
            <p className="mt-1 text-xs text-muted-foreground">{item.category ?? "Sin categoría"} · {item.definition_key}</p>
            <div className="mt-4 rounded-xl border bg-muted/20 p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{item.label}</p>
              <p className="mt-1 break-words text-lg font-semibold text-foreground">{item.value}</p>
              {item.raw_value && item.raw_value !== item.value ? <p className="mt-2 break-words text-xs text-muted-foreground">Original: {item.raw_value}</p> : null}
            </div>
            {editing ? (
              <div className="mt-4 space-y-3 rounded-xl border bg-card p-4">
                <div>
                  <label className="text-xs font-medium text-muted-foreground" htmlFor={`spec-value-${item.id}`}>Valor corregido</label>
                  <Input id={`spec-value-${item.id}`} className="mt-1" value={draftValue} onChange={(event) => setDraftValue(event.target.value)} />
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground" htmlFor={`spec-unit-${item.id}`}>Unidad</label>
                    <Input id={`spec-unit-${item.id}`} className="mt-1" value={draftUnit} onChange={(event) => setDraftUnit(event.target.value)} placeholder="Ej: GB, MHz, W" />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground" htmlFor={`spec-source-${item.id}`}>Fuente</label>
                    <Input id={`spec-source-${item.id}`} className="mt-1" value={draftSourceName} onChange={(event) => setDraftSourceName(event.target.value)} placeholder="Ej: ASUS" />
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground" htmlFor={`spec-url-${item.id}`}>URL de respaldo</label>
                  <Input id={`spec-url-${item.id}`} className="mt-1" value={draftSourceUrl} onChange={(event) => setDraftSourceUrl(event.target.value)} placeholder="https://..." />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground" htmlFor={`spec-note-${item.id}`}>Nota de revisión</label>
                  <textarea
                    id={`spec-note-${item.id}`}
                    className="mt-1 min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                    value={draftNote}
                    onChange={(event) => setDraftNote(event.target.value)}
                    placeholder="Qué se revisó o corrigió"
                  />
                </div>
              </div>
            ) : null}
          </div>
          <aside className="border-t bg-muted/20 p-4 sm:p-5 xl:border-l xl:border-t-0">
            <dl className="space-y-3 text-sm">
              <InfoRow label="Fuente" value={item.source_name || sourceLabel(item.source_type)} />
              <InfoRow label="Método" value={item.extraction_method || "No registrado"} />
              <InfoRow label="Historial" value={`${item.history_count} eventos`} />
            </dl>
            {item.source_url ? (
              <Button asChild variant="ghost" size="sm" className="mt-3 gap-2 px-0">
                <a href={item.source_url} target="_blank" rel="noreferrer">
                  Ver fuente <ExternalLink className="size-3.5" aria-hidden="true" />
                </a>
              </Button>
            ) : null}
            <Button variant="outline" className="mt-4 w-full" onClick={() => setEditing((value) => !value)} disabled={verifying}>
              {editing ? "Cancelar corrección" : "Corregir antes de verificar"}
            </Button>
            <Button className="mt-3 w-full gap-2" onClick={submitVerification} disabled={verifying} title={hasConflict ? "Verifica el valor actual o la corrección y resuelve el conflicto" : "Marcar como verificado"}>
              {verifying ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <ShieldCheck className="size-4" aria-hidden="true" />}
              {hasCorrection ? "Guardar y verificar" : hasConflict ? "Confirmar y resolver" : "Verificar"}
            </Button>
          </aside>
        </div>
      </CardContent>
    </Card>
  );
}

function buildCorrectionPayload(item: AdminSpecValue, draftValue: string, draftUnit: string, draftSourceName: string, draftSourceUrl: string, note: string): VerifySpecValuePayload {
  const value = draftValue.trim();
  const payload: VerifySpecValuePayload = {
    note,
    value_kind: item.value_kind || "text",
    raw_value: value,
    unit: draftUnit.trim() || null,
    source_type: "admin",
    source_name: draftSourceName.trim() || "Admin",
    source_url: draftSourceUrl.trim() || null,
    extraction_method: "admin_review",
  };

  if (item.value_kind === "number") {
    const normalizedNumber = Number(value.replace(",", ".").replace(/[^0-9.-]/g, ""));
    if (Number.isFinite(normalizedNumber)) {
      payload.value_number = normalizedNumber;
      return payload;
    }
  }

  if (item.value_kind === "boolean") {
    const normalized = value.toLowerCase();
    payload.value_boolean = ["true", "sí", "si", "yes", "1"].includes(normalized);
    return payload;
  }

  payload.value_kind = "text";
  payload.value_text = value;
  return payload;
}

function PlaceholderPanel({ section }: { section: AdminSection }) {
  const current = SECTIONS.find((item) => item.id === section);
  return (
    <Card className="shadow-none">
      <CardContent className="p-8">
        <div className="flex max-w-2xl gap-4">
          {current ? <current.Icon className="mt-1 size-6 text-primary" aria-hidden="true" /> : null}
          <div>
            <h2 className="text-xl font-semibold tracking-tight">{current?.label}</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Sección preparada para conectar backend específico. La navegación queda estable para escalar productos, categorías, tiendas, ofertas, ingesta y estadísticas sin rehacer `/admin`.
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyPanel({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-2xl border bg-muted/30 p-10 text-center">
      <CheckCircle2 className="mx-auto size-9 text-emerald-600" aria-hidden="true" />
      <h2 className="mt-3 font-semibold">{title}</h2>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
    </div>
  );
}

function LoadingPanel() {
  return (
    <div className="flex items-center gap-2 rounded-xl border bg-muted/30 p-6 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" aria-hidden="true" />
      Cargando administración...
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 break-words font-medium text-foreground">{value}</dd>
    </div>
  );
}

function statusLabel(status: string) {
  if (status === "review") return "Por revisar";
  if (status === "auto") return "Automático";
  if (status === "verified") return "Verificado";
  return status;
}

function sourceLabel(source: string) {
  const labels: Record<string, string> = {
    ai: "IA",
    admin: "Admin",
    manufacturer: "Fabricante",
    store: "Tienda",
    scraper: "Scraper",
    ingestion: "Ingesta",
    external: "Fuente externa",
  };
  return labels[source] ?? source;
}

function activityLabel(action: string) {
  const labels: Record<string, string> = {
    created: "Creado",
    value_changed: "Valor cambiado",
    source_updated: "Fuente actualizada",
    conflict_detected: "Conflicto",
    verified: "Verificado",
  };
  return labels[action] ?? action;
}
