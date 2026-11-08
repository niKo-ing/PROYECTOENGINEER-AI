// Prueba de carga con k6: hora pico de 10.000 usuarios activos al día.
//   k6 run -e URL=https://todobarato.cl -e TOKEN=<token de un usuario de prueba> servidor_propio/carga_10000.js
// Escenarios: ~1.000 personas navegando el catálogo y ~2 consultas de IA por segundo (18 a la vez).
import http from "k6/http";
import { check, sleep } from "k6";

const URL = __ENV.URL || "http://localhost";
const TOKEN = __ENV.TOKEN || "";
const BUSQUEDAS = ["notebook", "rtx", "ssd 1tb", "monitor 27", "ryzen", "celular", "teclado"];

export const options = {
  scenarios: {
    navegacion: {
      executor: "ramping-vus",
      exec: "navegar",
      stages: [
        { duration: "2m", target: 1000 },
        { duration: "10m", target: 1000 },
        { duration: "1m", target: 0 },
      ],
    },
    chat: {
      executor: "constant-arrival-rate",
      exec: "chatear",
      rate: 2, timeUnit: "1s", duration: "12m", startTime: "1m",
      preAllocatedVUs: 40, maxVUs: 120,
    },
  },
  thresholds: {
    "http_req_duration{tipo:catalogo}": ["p(95)<1000"],
    "http_req_duration{tipo:ia}": ["p(95)<15000"],
    "http_req_failed{tipo:catalogo}": ["rate<0.01"],
  },
};

export function navegar() {
  const q = BUSQUEDAS[Math.floor(Math.random() * BUSQUEDAS.length)];
  const tag = { tags: { tipo: "catalogo" } };
  const r1 = http.get(`${URL}/api/v1/categories`, tag);
  const r2 = http.get(`${URL}/api/v1/products?query=${encodeURIComponent(q)}&limit=20`, tag);
  check(r1, { "categorías 200": (r) => r.status === 200 });
  check(r2, { "búsqueda 200": (r) => r.status === 200 });
  const items = r2.status === 200 ? r2.json("items") : [];
  if (items && items.length) {
    const id = items[Math.floor(Math.random() * items.length)].id;
    http.get(`${URL}/api/v1/products/${id}`, tag);
    http.get(`${URL}/api/v1/products/${id}/offers`, tag);
  }
  sleep(5 + Math.random() * 15); // una persona lee la página antes de seguir
}

export function chatear() {
  const r = http.post(`${URL}/api/v1/ai/chat`, JSON.stringify({ message: "¿Qué notebook me recomiendas por menos de 600 mil?" }), {
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${TOKEN}` },
    tags: { tipo: "ia" },
    timeout: "60s",
  });
  check(r, { "chat 200 o 429/503 controlado": (x) => [200, 429, 503].includes(x.status) });
}
