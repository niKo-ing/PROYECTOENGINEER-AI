import { newId } from "@/lib/utils";

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

export type AgentProductCard = {
  id: number;
  name: string;
  brand: string | null;
  category: string | null;
  image_url: string | null;
  lowest_price: number | null;
  lowest_price_store: string | null;
  price_clp: number | null;
  rating: number | null;
  offer_count: number | null;
};

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
  products?: AgentProductCard[];
  comparison?: Record<string, unknown> | null;
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

function headersFor(accessToken: string): HeadersInit {
  return { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` };
}

async function parse<T>(response: Response): Promise<T> {
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string"
        ? payload.detail
        : response.status >= 500
          ? "El servidor tardó demasiado o no respondió. Espera unos segundos y vuelve a intentarlo."
          : "No fue posible completar la solicitud. Inténtalo nuevamente.";
    throw new Error(detail);
  }
  return payload as T;
}

export async function runAgent(message: string, threadId: string, accessToken: string, productId?: number | null): Promise<AgentRun> {
  const response = await fetch(`${BASE}/run`, {
    method: "POST",
    headers: headersFor(accessToken),
    body: JSON.stringify({ message, thread_id: threadId, ...(productId ? { product_id: productId } : {}) }),
  });
  return parse<AgentRun>(response);
}

export async function fetchAgentState(accessToken: string): Promise<AgentState> {
  const response = await fetch(`${BASE}/estado`, { headers: headersFor(accessToken), cache: "no-store" });
  return parse<AgentState>(response);
}

export function newThreadId(): string {
  return `web-${newId().slice(0, 8)}`;
}
