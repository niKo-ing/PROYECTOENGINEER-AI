type AuthMode = "login" | "register";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function errorCode(error: unknown): string | undefined {
  return isRecord(error) && typeof error.code === "string" ? error.code : undefined;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (isRecord(error) && typeof error.message === "string") return error.message;
  return "";
}

function errorStatus(error: unknown): number | undefined {
  return isRecord(error) && typeof error.status === "number" ? error.status : undefined;
}

const NETWORK_HINTS = ["failed to fetch", "fetch failed", "network", "load failed", "econnrefused"];

function isNetworkError(error: unknown): boolean {
  if (error instanceof TypeError) return true;
  if (isRecord(error) && error.name === "AuthRetryableFetchError") return true;
  const message = errorMessage(error).toLowerCase();
  return NETWORK_HINTS.some((hint) => message.includes(hint));
}

function isConfigurationError(error: unknown): boolean {
  const status = errorStatus(error);
  const code = errorCode(error);
  const message = errorMessage(error).toLowerCase();
  return (
    status === 420 ||
    code === "invalid_api_key" ||
    code === "bad_jwt" ||
    message.includes("invalid api key") ||
    message.includes("invalid jwt") ||
    message.includes("project not found") ||
    message.includes("apikey")
  );
}

function isRateLimitError(error: unknown): boolean {
  const status = errorStatus(error);
  const code = errorCode(error);
  const message = errorMessage(error).toLowerCase();
  return (
    status === 429 ||
    code === "over_request_rate_limit" ||
    code === "over_email_send_rate_limit" ||
    code === "over_sms_send_rate_limit" ||
    message.includes("rate limit")
  );
}

export function getFriendlyAuthMessage(error: unknown, mode: AuthMode): string {
  if (isNetworkError(error)) {
    return "No pudimos conectarnos con el servicio. Verificá tu conexión e intentá de nuevo.";
  }

  if (isConfigurationError(error)) {
    return "El servicio de autenticación tiene un problema de configuración. Intentá más tarde.";
  }

  if (isRateLimitError(error)) {
    return "Demasiados intentos. Esperá unos minutos y volvé a intentar.";
  }

  if (mode === "login") {
    if (errorCode(error) === "invalid_credentials") {
      return "Correo o contraseña incorrectos.";
    }
    if (errorCode(error) === "email_not_confirmed") {
      return "Todavía no confirmaste tu correo electrónico. Revisá tu bandeja de entrada.";
    }
    return "No pudimos iniciar sesión. Intentá de nuevo.";
  }

  switch (errorCode(error)) {
    case "email_exists":
    case "user_already_exists":
      return "Ya existe una cuenta con ese correo. Probá iniciar sesión.";
    case "weak_password":
      return "La contraseña es demasiado débil. Usá al menos 6 caracteres.";
    case "email_address_invalid":
      return "El correo electrónico ingresado no es válido.";
    case "signup_disabled":
      return "El registro está deshabilitado temporalmente.";
    case "email_not_confirmed":
      return "Todavía no confirmaste tu correo. Revisá tu bandeja de entrada.";
    default:
      return "No pudimos crear la cuenta. Intentá de nuevo.";
  }
}