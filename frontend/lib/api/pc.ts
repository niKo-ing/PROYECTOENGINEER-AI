// Cliente del armador de PC, el asistente con IA, «Mis computadores», las guías, la privacidad y la observabilidad.

export type SlotKey = "cpu" | "motherboard" | "ram" | "gpu" | "storage" | "psu" | "case" | "cooler";

export type SlotInfo = { key: SlotKey; label: string; required: boolean; multiple: boolean };
export type UseCaseInfo = { key: string; label: string; description: string };

export type Part = {
  slot: SlotKey;
  name: string;
  specs: Record<string, unknown>;
  product_id: number | null;
  price_clp: number | null;
  brand: string | null;
  store: string | null;
  legacy: boolean;
};

export type Issue = { level: "error" | "warning" | "info"; code: string; message: string; slots: SlotKey[] };

export type CompatibilityReport = {
  compatible: boolean;
  complete: boolean;
  issues: Issue[];
  missing: SlotKey[];
  missing_labels: string[];
  estimated_watts: number;
  recommended_psu_w: number;
  total_clp: number;
  summary: string;
  checks_run?: string[];
};

export type PartOption = Part & { compatible: boolean; issues: Issue[] };

export type BuildItem = { slot: SlotKey; product_id?: number | null; name?: string; specs?: Record<string, unknown> };

export type Recommendation = {
  needs: { use_case: string; budget_clp: number; cpu_brand: string | null; gpu_brand: string | null; wifi: boolean; small: boolean };
  use_case_label: string;
  items: Part[];
  report: CompatibilityReport;
  score: number;
  within_budget: boolean;
  total_clp: number;
  leftover_clp: number;
  reasons: Partial<Record<SlotKey, string>>;
  alternatives: Record<string, { budget_clp: number; total_clp: number; score: number; cpu: string; gpu: string | null }>;
};

export type GuideRef = { guide: string; title: string; url: string; content: string };

export type AssistantTurn = { role: "user" | "assistant"; content: string };
export type AssistantNeeds = Partial<{ use_case: string; budget_clp: number; cpu_brand: string; gpu_brand: string; wifi: boolean; small: boolean }>;
export type AssistantOption = { label: string; value: string | number; field: "use_case" | "budget_clp" };

export type AssistantReply = {
  state: "question" | "build" | "blocked";
  answer: string;
  needs: AssistantNeeds;
  missing: string[];
  options: AssistantOption[];
  recommendation?: Recommendation;
  guides?: GuideRef[];
  source?: "llm" | "reglas";
  explained_by?: "llm" | "reglas";
  /** Reglas automáticas que Gemini anuló (uso o presupuesto) con confianza alta y una cita verificada del usuario. */
  overrides?: AssistantOverride[];
  run_id: string;
};

export type AssistantOverride = {
  field: "use_case" | "budget_clp";
  rule: string;
  rules_value: string | number;
  llm_value: string | number;
  quote: string;
  message: string;
};

export type SavedPc = {
  id: number;
  name: string;
  kind: "propio" | "proyecto";
  use_case: string | null;
  use_case_label: string | null;
  budget_clp: number | null;
  notes: string | null;
  source: "manual" | "asistente" | "agente";
  items: Part[];
  total_clp: number;
  created_at: string | null;
  updated_at: string | null;
  report?: CompatibilityReport;
};

export type UpgradeOption = {
  title: string;
  buy: Part[];
  replaces: SlotKey[];
  cost_clp: number;
  score_before: number;
  score_after: number;
  gain_pct: number;
  report: CompatibilityReport;
};

export type Upgrades = { pc_id: number; use_case: string; budget_clp: number; score_now: number; options: UpgradeOption[] };
export type Review = { pc: SavedPc; upgrades: Upgrades | null; answer: string; guides: GuideRef[]; explained_by: "llm" | "reglas"; run_id: string };

export type GuideSummary = { slug: string; title: string; summary: string };
export type Guide = GuideSummary & { body: string; others: { slug: string; title: string }[] };
export type GuideHit = GuideRef & { keyword_score: number | null; semantic_score: number | null };

const BASE = "/api/v1";

type RequestOptions = { method?: string; body?: unknown; token?: string | null };

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, { method = "GET", body, token }: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${BASE}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), cache: "no-store" });
  if (response.status === 204) return undefined as T;
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof payload === "object" && payload !== null && "detail" in payload ? (payload as { detail: unknown }).detail : null;
    const message =
      typeof detail === "string"
        ? detail
        : response.status === 401
          ? "Tu sesión expiró. Vuelve a iniciar sesión."
          : response.status === 429
            ? "Hiciste muchas consultas seguidas. Espera un momento."
            : response.status >= 500
              ? "El servidor no respondió. Inténtalo de nuevo en unos segundos."
              : "No fue posible completar la solicitud.";
    throw new ApiError(message, response.status);
  }
  return payload as T;
}

// ── Armador ──────────────────────────────────────────────────────────────────────────────────────
export const fetchSlots = () => request<{ slots: SlotInfo[]; use_cases: UseCaseInfo[] }>("/pc/slots");
export const fetchOptions = (slot: SlotKey, items: BuildItem[], includeLegacy = false) =>
  request<{ slot: SlotKey; items: PartOption[] }>("/pc/options", { method: "POST", body: { slot, items, include_legacy: includeLegacy } });
export const checkCompatibility = (items: BuildItem[]) =>
  request<{ items: Part[]; report: CompatibilityReport }>("/pc/compatibility", { method: "POST", body: { items } });
export const recommendPc = (needs: { use_case: string; budget_clp: number; cpu_brand?: string | null; gpu_brand?: string | null; wifi?: boolean; small?: boolean }) =>
  request<Recommendation>("/pc/recommend", { method: "POST", body: needs });

// ── Asistente con IA ─────────────────────────────────────────────────────────────────────────────
export const askAssistant = (messages: AssistantTurn[], needs: AssistantNeeds, token: string) =>
  request<AssistantReply>("/pc/assistant", { method: "POST", body: { messages, needs }, token });

// ── Mis computadores ─────────────────────────────────────────────────────────────────────────────
export type PcPayload = { name: string; kind: "propio" | "proyecto"; use_case?: string | null; budget_clp?: number | null; notes?: string | null; items: BuildItem[]; source?: SavedPc["source"] };
export const listMyPcs = (token: string) => request<{ items: SavedPc[] }>("/me/pcs", { token });
export const getMyPc = (id: number, token: string) => request<SavedPc>(`/me/pcs/${id}`, { token });
export const createPc = (payload: PcPayload, token: string) => request<SavedPc>("/me/pcs", { method: "POST", body: payload, token });
export const updatePc = (id: number, payload: Partial<PcPayload>, token: string) => request<SavedPc>(`/me/pcs/${id}`, { method: "PATCH", body: payload, token });
export const deletePc = (id: number, token: string) => request<void>(`/me/pcs/${id}`, { method: "DELETE", token });
export const reviewPc = (id: number, budget_clp: number, use_case: string | null, token: string) =>
  request<Review>(`/me/pcs/${id}/review`, { method: "POST", body: { budget_clp, use_case }, token });

// ── Guías ────────────────────────────────────────────────────────────────────────────────────────
export const fetchGuides = () => request<{ items: GuideSummary[] }>("/pc/guides");
export const fetchGuide = (slug: string) => request<Guide>(`/pc/guides/${encodeURIComponent(slug)}`);
export const searchGuides = (q: string) => request<{ query: string; items: GuideHit[] }>(`/pc/guides/search?q=${encodeURIComponent(q)}`);

// ── Privacidad ───────────────────────────────────────────────────────────────────────────────────
export const exportMyData = (token: string) => request<Record<string, unknown>>("/me/data", { token });
export const deleteMyData = (token: string) =>
  request<{ deleted: Record<string, number>; account_deleted: boolean }>("/me/data", { method: "DELETE", body: { confirm: "BORRAR", delete_account: true }, token });

// ── Observabilidad ───────────────────────────────────────────────────────────────────────────────
export type Latency = { n?: number; p50: number | null; p95: number | null; p99?: number | null; mean?: number | null; max?: number | null };
export type Slo = { key: string; label: string; value: number | null; target: number; op: "<=" | ">="; unit: "ms" | "ratio"; state: "ok" | "alerta" | "sin_datos" };
export type RunRow = {
  run_id: string;
  flow: string;
  started_at: string | null;
  latency_ms: number;
  status: "ok" | "error" | "fallback" | "blocked";
  error_type: string | null;
  model: string | null;
  llm_calls: number;
  input_tokens: number;
  output_tokens: number;
  tool_calls: number;
  tool_errors: number;
  tools: string[];
  replans: number;
  input_preview: string | null;
  guardrails: { injection?: boolean; blocked?: boolean };
  quality: { precios?: { cited: number; ok: boolean; unsupported?: number[] } } & Record<string, unknown>;
  eval_tag: string | null;
};
export type Span = { seq: number; kind: "llm" | "tool" | "stage"; name: string; start_ms: number; duration_ms: number; status: string; input_tokens: number | null; output_tokens: number | null; detail: Record<string, unknown> };
export type RunDetail = RunRow & { cpu_ms: number | null; error_message: string | null; extra: Record<string, unknown>; spans: Span[] };
export type Metrics = {
  window_hours: number;
  generated_at: string;
  summary: {
    runs: number;
    status: Record<string, number>;
    error_rate: number | null;
    fallback_rate: number | null;
    latency_ms: Latency;
    by_flow: Record<string, { runs: number; latency_ms: Latency; error_rate: number | null; fallback_rate: number | null }>;
    llm: { calls: number; calls_per_run: number | null; latency_ms: Latency; input_tokens: number; output_tokens: number; tokens_per_run: number | null; errors: number };
    cpu_ms: Latency;
    tools: Record<string, { calls: number; errors: number; error_rate: number | null; p50_ms: number | null; p95_ms: number | null }>;
    stages: Record<string, { n: number; p50_ms: number | null; p95_ms: number | null }>;
    quality: { answers_with_prices: number; grounded_rate: number | null; unsupported_prices: number; explanations_discarded: number; invented_budget_discarded: number; rules_llm_disagreement: number; rules_llm_disagreement_rate: number | null; rules_overridden_by_llm: number; budget_warning_added: number; replans: number; tool_errors: number };
    security: { injection_detected: number; blocked: number };
  };
  slo: Slo[];
  timeseries: { t: string; runs: number; p50_ms: number | null; p95_ms: number | null; errors: number; fallbacks: number; tokens: number }[];
  recent: RunRow[];
};

export const fetchMetrics = (token: string, hours: number, includeEval: boolean) =>
  request<Metrics>(`/observability/metrics?hours=${hours}&include_eval=${includeEval}`, { token });
export const fetchRun = (runId: string, token: string) => request<RunDetail>(`/observability/runs/${runId}`, { token });

// ── utilidades ───────────────────────────────────────────────────────────────────────────────────
export const SLOT_ORDER: SlotKey[] = ["cpu", "motherboard", "ram", "gpu", "storage", "psu", "case", "cooler"];

export function itemsFromParts(parts: Part[]): BuildItem[] {
  return parts.map((part) => (part.product_id ? { slot: part.slot, product_id: part.product_id } : { slot: part.slot, name: part.name, specs: part.specs }));
}

const DRAFT_KEY = "todobarato.armado";

/** Pasa un armado entre páginas (asistente → armador) sin meterlo en la URL. */
export function saveDraft(items: BuildItem[], meta: { name?: string; use_case?: string | null; budget_clp?: number | null; pcId?: number; kind?: "propio" | "proyecto" } = {}) {
  try {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ items, ...meta }));
  } catch {
    // Sin almacenamiento el armador parte vacío.
  }
}

export function takeDraft(): { items: BuildItem[]; name?: string; use_case?: string | null; budget_clp?: number | null; pcId?: number; kind?: "propio" | "proyecto" } | null {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(DRAFT_KEY);
    return JSON.parse(raw);
  } catch {
    return null;
  }
}
