/**
 * Sesión con las cuentas propias del backend (`/api/v1/auth/*`). Reemplaza a supabase-js, cuyo proyecto ya no
 * existe, y conserva la forma de su API (`getSession`, `signInWithPassword`, `signUp`, `signOut`,
 * `onAuthStateChange`) para que las vistas cambien lo mínimo.
 *
 * El token se guarda en localStorage: la app no tiene cookies de sesión propias y el backend valida la firma,
 * el emisor y el vencimiento en cada llamada.
 */

export type SessionUser = {
  id: string;
  email: string;
  user_metadata: { name?: string };
};

export type Session = {
  access_token: string;
  expires_at: number; // segundos desde 1970
  user: SessionUser;
};

export type AuthError = { message: string; status?: number; code?: string };

type AuthResult = { data: { session: Session | null }; error: AuthError | null };
type Listener = (event: "SIGNED_IN" | "SIGNED_OUT", session: Session | null) => void;

const STORAGE_KEY = "todobarato.sesion";
const listeners = new Set<Listener>();

function read(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as Session;
    if (!session.access_token || session.expires_at * 1000 <= Date.now()) {
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

function write(session: Session | null) {
  try {
    if (session) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Navegación privada sin almacenamiento: la sesión dura lo que la pestaña.
  }
  listeners.forEach((listener) => listener(session ? "SIGNED_IN" : "SIGNED_OUT", session));
}

const CODES: Record<number, string> = {
  401: "invalid_credentials",
  409: "user_already_exists",
  422: "weak_password",
  429: "over_request_rate_limit",
};

async function request(path: string, body: unknown): Promise<AuthResult> {
  let response: Response;
  try {
    response = await fetch(`/api/v1/auth/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (error) {
    return { data: { session: null }, error: { message: error instanceof Error ? error.message : "network", code: "network" } };
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string"
        ? payload.detail
        : `HTTP ${response.status}`;
    return { data: { session: null }, error: { message: detail, status: response.status, code: CODES[response.status] } };
  }
  const data = payload as { access_token: string; expires_in: number; user: { id: string; email: string; display_name: string | null } };
  const session: Session = {
    access_token: data.access_token,
    expires_at: Math.floor(Date.now() / 1000) + data.expires_in,
    user: { id: data.user.id, email: data.user.email, user_metadata: { name: data.user.display_name ?? undefined } },
  };
  write(session);
  return { data: { session }, error: null };
}

export const auth = {
  async getSession(): Promise<{ data: { session: Session | null }; error: null }> {
    return { data: { session: read() }, error: null };
  },
  signInWithPassword(values: { email: string; password: string }) {
    return request("login", values);
  },
  signUp(values: { email: string; password: string; name: string }) {
    return request("register", { email: values.email, password: values.password, display_name: values.name });
  },
  async signOut() {
    write(null);
  },
  onAuthStateChange(listener: Listener) {
    listeners.add(listener);
    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) listener(read() ? "SIGNED_IN" : "SIGNED_OUT", read());
    };
    window.addEventListener("storage", onStorage);
    return {
      data: {
        subscription: {
          unsubscribe() {
            listeners.delete(listener);
            window.removeEventListener("storage", onStorage);
          },
        },
      },
    };
  },
};

/** Lee el token actual (para llamadas a la API fuera de React). */
export function currentAccessToken(): string | null {
  return read()?.access_token ?? null;
}
