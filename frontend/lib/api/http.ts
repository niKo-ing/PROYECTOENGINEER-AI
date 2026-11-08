// Lecturas del catálogo con reintento.
//
// En la EP2, cuando un servidor se caía de golpe, el balanceador seguía mandándole visitas unos segundos
// y el usuario veía errores 502. Una lectura (GET) se puede repetir sin riesgo: si falla por un error
// pasajero (502, 503, 504 o la red), se reintenta y el segundo intento llega al servidor que sigue vivo.
// Un 429 (límite de uso) se respeta: se espera lo que indique Retry-After, con un máximo.

const RETRYABLE = new Set([502, 503, 504]);
const DELAYS_MS = [300, 1000];
const MAX_RETRY_AFTER_MS = 3000;

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function getWithRetry(url: string, init: RequestInit = {}): Promise<Response> {
  for (let attempt = 0; ; attempt++) {
    const last = attempt >= DELAYS_MS.length;
    try {
      // El servidor responde Cache-Control: el navegador puede reutilizar la respuesta unos segundos.
      const response = await fetch(url, { cache: "default", ...init });
      if (last) return response;
      if (RETRYABLE.has(response.status)) {
        await wait(DELAYS_MS[attempt]);
        continue;
      }
      if (response.status === 429) {
        const seconds = Number(response.headers.get("Retry-After") ?? "1");
        await wait(Math.min(Number.isFinite(seconds) ? seconds * 1000 : 1000, MAX_RETRY_AFTER_MS));
        continue;
      }
      return response;
    } catch (error) {
      if (last) throw error;
      await wait(DELAYS_MS[attempt]);
    }
  }
}
