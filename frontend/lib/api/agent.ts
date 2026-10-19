export type AgentMode = "demo" | "real";

export type PlanStep = {
  id: number;
  action: string;
  priority: number;
  status: "pendiente" | "hecho" | string;
};

export type TraceEvent =
  | { turn: number; node: "recall"; memories: { content: string; relevance: number }[]; budget_clp: number | null }
  | { turn: number; node: "plan"; source: string; replan: string | null; plan: string[] }
  | { turn: number; node: "act"; step: number; tool_calls: { tool: string; args: Record<string, unknown> }[] }
  | {
      turn: number;
      node: "reflect";
      observed: string[];
      diagnosis: { reason: string; detail: string } | null;
      decision?: "replanificar" | "continuar_sin_replan";
    }
  | { turn: number; node: "give_up"; max_steps: number }
  | { turn: number; node: "remember"; stored: string[] };

export type AgentRun = {
  thread_id: string;
  answer: string;
  plan: PlanStep[];
  plan_source: string;
  tools_used: string[];
  wrote: string[];
  replans: number;
  memories_used: string[];
  steps: number;
  trace: TraceEvent[];
};

export type AgentAlert = {
  id: number;
  product: string;
  target_price_clp: number;
  current_price_clp: number | null;
  active: boolean;
  triggered_price_clp: number | null;
};

export type AgentList = {
  id: number;
  name: string;
  total_clp: number;
  budget_clp: number | null;
  items: { name: string; price_clp: number; store: string }[];
};

export type AgentMemory = { id: number; kind: string; content: string; importance: number };

export type AgentState = { alerts: AgentAlert[]; lists: AgentList[]; memories: AgentMemory[] };

export const EMPTY_STATE: AgentState = { alerts: [], lists: [], memories: [] };

const BASE = "/api/v1/agent";

function pathFor(mode: AgentMode, route: string) {
  return mode === "demo" ? `${BASE}/demo${route}` : `${BASE}${route}`;
}

function headersFor(mode: AgentMode, accessToken?: string): HeadersInit {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (mode === "real" && accessToken) headers.Authorization = `Bearer ${accessToken}`;
  return headers;
}

async function parse<T>(response: Response): Promise<T> {
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string"
        ? payload.detail
        : "No fue posible completar la solicitud. Inténtalo nuevamente.";
    throw new Error(detail);
  }
  return payload as T;
}

export async function runAgent(mode: AgentMode, message: string, threadId: string, accessToken?: string): Promise<AgentRun> {
  const response = await fetch(pathFor(mode, "/run"), {
    method: "POST",
    headers: headersFor(mode, accessToken),
    body: JSON.stringify({ message, thread_id: threadId }),
  });
  return parse<AgentRun>(response);
}

export async function fetchAgentState(mode: AgentMode, accessToken?: string): Promise<AgentState> {
  const response = await fetch(pathFor(mode, "/estado"), { headers: headersFor(mode, accessToken), cache: "no-store" });
  return parse<AgentState>(response);
}

export async function isDemoAvailable(): Promise<boolean> {
  try {
    const response = await fetch(`${BASE}/demo/disponible`, { cache: "no-store" });
    if (!response.ok) return false;
    const payload = (await response.json()) as { enabled?: boolean };
    return payload.enabled === true;
  } catch {
    return false;
  }
}

export async function dropDemoPrice(): Promise<{ product: string; before_clp: number; after_clp: number }> {
  return parse(await fetch(`${BASE}/demo/bajar-precio`, { method: "POST" }));
}

export async function resetDemo(): Promise<void> {
  await parse(await fetch(`${BASE}/demo/reiniciar`, { method: "POST" }));
}

export function newThreadId(): string {
  return `web-${crypto.randomUUID().slice(0, 8)}`;
}
