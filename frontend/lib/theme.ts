// Tema claro/oscuro. La paleta oscura vive en `.dark` (app/globals.css); aquí solo se decide cuándo aplicarla.
// Sin elección guardada, se sigue al sistema (y a sus cambios en vivo); el botón del encabezado guarda una elección.

export const THEME_KEY = "todobarato.tema";

export type Theme = "light" | "dark";

/** Script que corre en <head> antes de pintar: evita el destello del tema claro al cargar en oscuro. */
export const THEME_SCRIPT = `(function () {
  var root = document.documentElement;
  var media = window.matchMedia("(prefers-color-scheme: dark)");
  function saved() { try { return localStorage.getItem("${THEME_KEY}"); } catch (e) { return null; } }
  function apply(dark) { root.classList.toggle("dark", dark); root.style.colorScheme = dark ? "dark" : "light"; }
  var choice = saved();
  apply(choice ? choice === "dark" : media.matches);
  media.addEventListener("change", function (event) { if (!saved()) apply(event.matches); });
})();`;

export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Navegación privada o almacenamiento bloqueado: el tema cambia igual, solo no se recuerda.
  }
}

/** Suscripción a los cambios de la clase `dark` en <html> (botón, sistema u otra pestaña con el script). */
export function subscribeTheme(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => observer.disconnect();
}

export function currentTheme(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}
