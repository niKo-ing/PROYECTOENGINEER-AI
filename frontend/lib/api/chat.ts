export type ResearchSource = {
  source_type: string;
  source_name: string;
  source_url: string | null;
  title: string | null;
  content: string | null;
  confidence: number;
  kind: string;
  retrieved_at: string;
};

export type ChatResult = {
  answer: string;
  tools_used: string[];
  usage: {
    model: string;
    input_tokens: number | null;
    output_tokens: number | null;
    latency_ms: number | null;
  } | null;
  sources?: ResearchSource[];
  research?: boolean;
};

export async function sendChatMessage(message: string, accessToken: string, productId?: number | null): Promise<ChatResult> {
  const body: Record<string, unknown> = { message };
  if (productId) body.product_id = productId;

  const response = await fetch("/api/v1/ai/chat", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string"
      ? payload.detail
      : "No fue posible obtener una respuesta. Inténtalo nuevamente.";
    throw new Error(detail);
  }

  if (!isChatResult(payload)) {
    throw new Error("El servidor devolvió una respuesta inválida.");
  }
  return payload;
}

function isChatResult(value: unknown): value is ChatResult {
  return typeof value === "object" && value !== null && "answer" in value && typeof value.answer === "string" && "tools_used" in value && Array.isArray(value.tools_used);
}
