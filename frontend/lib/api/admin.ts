import type { AdminDashboardResponse, AdminSpecReviewResponse, AdminSpecValue } from "@/types/admin";

export interface VerifySpecValuePayload {
  note?: string;
  value_kind?: string;
  raw_value?: string | null;
  value_text?: string | null;
  value_number?: number | null;
  value_boolean?: boolean | null;
  unit?: string | null;
  source_type?: string;
  source_name?: string | null;
  source_url?: string | null;
  extraction_method?: string | null;
}

export async function fetchAdminDashboard(accessToken: string): Promise<AdminDashboardResponse> {
  const response = await fetch("/api/v1/admin/dashboard", {
    cache: "no-store",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) throw new Error(await errorMessage(response, "No fue posible cargar el dashboard."));
  return response.json();
}

export async function fetchSpecReviewQueue(accessToken: string): Promise<AdminSpecReviewResponse> {
  const response = await fetch("/api/v1/admin/spec-values/review", {
    cache: "no-store",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!response.ok) throw new Error(await errorMessage(response, "No fue posible cargar la cola de revisión."));
  return response.json();
}

export async function verifySpecValue(accessToken: string, valueId: number, payload?: VerifySpecValuePayload): Promise<AdminSpecValue> {
  const response = await fetch(`/api/v1/admin/spec-values/${valueId}/verify`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload ?? { note: "Verificado desde /admin" }),
  });
  if (!response.ok) throw new Error(await errorMessage(response, "No fue posible verificar el dato."));
  return response.json();
}

async function errorMessage(response: Response, fallback: string) {
  const payload: unknown = await response.json().catch(() => null);
  if (typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string") {
    return payload.detail;
  }
  return fallback;
}
