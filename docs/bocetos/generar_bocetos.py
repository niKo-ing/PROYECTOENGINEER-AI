"""Genera los bocetos (wireframes de baja fidelidad) de las tres pantallas principales en SVG.

    python docs/bocetos/generar_bocetos.py

Cajas grises con su contenido y anotaciones en azul que explican cada decisión de diseño. Son el plano de las pantallas
construidas en ``frontend/app/`` (capturas reales en ``docs/entrega/capturas/``).
"""

from html import escape
from pathlib import Path

GRIS, BORDE, TEXTO, SUAVE, NOTA = "#f3f4f6", "#9ca3af", "#1f2937", "#6b7280", "#2563eb"


class Boceto:
    def __init__(self, ancho: int, alto: int, titulo: str):
        self.ancho, self.alto, self.partes = ancho, alto, []
        self.texto(24, 34, titulo, 20, peso=700)

    def caja(self, x, y, w, h, etiqueta="", relleno=GRIS, punteada=False, radio=10, tam=13, centro=False):
        guion = ' stroke-dasharray="6 4"' if punteada else ""
        self.partes.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radio}" fill="{relleno}" stroke="{BORDE}"{guion}/>')
        if etiqueta:
            for i, linea in enumerate(etiqueta.split("\n")):
                if centro:
                    self.texto(x + w / 2, y + h / 2 + 5 + i * (tam + 4), linea, tam, ancla="middle")
                else:
                    self.texto(x + 12, y + 22 + i * (tam + 5), linea, tam)

    def texto(self, x, y, contenido, tam=13, color=TEXTO, peso=400, ancla="start"):
        self.partes.append(f'<text x="{x}" y="{y}" font-size="{tam}" fill="{color}" font-weight="{peso}" text-anchor="{ancla}" style="white-space:pre">{escape(contenido)}</text>')

    def linea(self, x1, y1, x2, y2, color=BORDE):
        self.partes.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2"/>')

    def nota(self, x, y, contenido, hacia=None):
        """Anotación de diseño en azul, con flecha opcional hacia (x, y)."""
        for i, linea in enumerate(contenido.split("\n")):
            self.texto(x, y + i * 17, linea, 12.5, NOTA)
        if hacia:
            self.partes.append(f'<line x1="{x - 6}" y1="{y - 4}" x2="{hacia[0]}" y2="{hacia[1]}" stroke="{NOTA}" stroke-width="1.5" marker-end="url(#flecha)"/>')

    def svg(self) -> str:
        defs = f'<defs><marker id="flecha" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="{NOTA}"/></marker></defs>'
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.ancho} {self.alto}" width="{self.ancho}" height="{self.alto}" '
                f'font-family="DejaVu Sans, Arial, sans-serif"><rect width="100%" height="100%" fill="#fff"/>{defs}{"".join(self.partes)}</svg>\n')


def asistente() -> str:
    b = Boceto(1280, 760, "Boceto 1 · Asistente (/chat): el razonamiento se pliega dentro de la respuesta")
    b.caja(24, 56, 860, 44, "Asistente de ahorro                                            [ Guardado (3) ]   [ Nueva conversación ]")
    b.caja(560, 120, 300, 40, "Quiero un notebook gamer, tengo $300.000", relleno="#e5e7eb")
    b.caja(60, 180, 800, 330, "")
    b.texto(76, 206, "✦ Pensó en 7 pasos · cambió de plan 2 veces  ›", 13, SUAVE)
    b.caja(76, 220, 560, 82, "1. Buscó «notebook gamer» en el catálogo hasta $300.000\n2. Cambió de plan: no encontró resultados y amplió la búsqueda\n3. Revisó las ofertas…   ·   Ver detalle técnico", relleno="#fff", punteada=True, tam=12)
    b.caja(76, 316, 760, 50, "Respuesta en texto: el más barato cuesta $349.990, faltan $49.990; dejé una alerta.", relleno="#fff")
    for i in range(3):
        b.caja(76 + i * 190, 380, 176, 80, f"Tarjeta de producto {i + 1}\nprecio · tienda", relleno="#fff", tam=12)
    b.caja(76, 472, 190, 28, "✓ Alerta creada · ver", relleno="#dbeafe", radio=14, tam=12)
    b.caja(60, 640, 800, 52, "Escribe tu consulta…                                                                  [ Enviar ]")
    b.caja(910, 56, 346, 636, "Detalle técnico (a pedido)\n\nPlan con prioridades P1–P3\nHerramientas y argumentos\nReplanes y memoria usada", punteada=True)
    b.nota(910, 712, "Panel lateral: solo se abre con «Ver detalle técnico».\nEs lo que se muestra al docente: plan y trazas.")
    b.nota(652, 236, "Plegado por defecto: el usuario\nve la respuesta, no el registro.", hacia=(640, 236))
    b.nota(280, 492, "Lo escrito en la cuenta se confirma aquí;\n«Guardado» abre una ventana aparte.", hacia=(268, 486))
    return b.svg()


def observabilidad() -> str:
    b = Boceto(1280, 840, "Boceto 2 · Panel de observabilidad (/observabilidad, solo administradores)")
    b.caja(24, 56, 420, 40, "[ 24 h | 7 días | 30 días ]   ☑ incluir evaluación   ↻")
    b.caja(24, 112, 260, 176, "Latencia p95\n\n  5,6 s\n\np99 · máximo", tam=15)
    nombres = ["Ejecuciones", "Mediana de latencia", "Tasa de error", "Respuestas con respaldo",
               "Precios con respaldo", "Llamadas a Gemini", "Tokens por ejecución", "Intentos de inyección"]
    for i, n in enumerate(nombres):
        b.caja(300 + (i % 4) * 240, 112 + (i // 4) * 92, 228, 80, f"{n}\n  valor")
    b.texto(24, 316, "Objetivos de servicio y alertas", 14, SUAVE, 700)
    for i, n in enumerate(["p95 ≤ 8 s", "error ≤ 5 %", "respaldo ≤ 20 %", "precios ≥ 95 %"]):
        b.caja(24 + i * 310, 328, 296, 70, f"✓ Cumple / ✗ Alerta\n{n} · valor actual")
    b.caja(24, 420, 610, 200, "Ejecuciones en el tiempo (barras)")
    b.caja(650, 420, 606, 200, "Latencia p50 y p95 en el tiempo (líneas)")
    b.caja(24, 640, 400, 150, "Por flujo: agente / asistente /\nrevisión de PC (n, p50, p95, error)")
    b.caja(440, 640, 400, 150, "Por herramienta y por etapa\n(llamadas, p95, errores)")
    b.caja(856, 640, 400, 150, "Cascada de una ejecución:\nentender → recomendar → guías →\nexplicar (Gemini) en ms")
    b.nota(300, 300, "La métrica que manda (p95) va primero y más grande.", hacia=(286, 296))
    b.nota(24, 818, "Exportable a Prometheus/Grafana: GET /observability/prometheus")
    return b.svg()


def armador() -> str:
    b = Boceto(1280, 720, "Boceto 3 · Armador de PC (/armar): la compatibilidad la decide el motor de reglas")
    b.caja(24, 56, 1232, 70, "Partir de una recomendación: [ uso ▾ ]   Presupuesto: [ 800000 ]   [ Armar por mí ]        [ Prefiero que la IA me pregunte ]")
    for i, pieza in enumerate(["Procesador", "Placa madre", "Memoria RAM", "Tarjeta gráfica", "Almacenamiento", "Fuente de poder", "Gabinete", "Refrigeración"]):
        b.caja(24, 146 + i * 66, 230, 56, f"{pieza}\nelegida / elegir", tam=12)
    b.caja(274, 146, 620, 40, "Filtrar por modelo o marca…", relleno="#fff")
    for i in range(5):
        aviso = "\n✗ no calza: socket AM5 ≠ AM4" if i == 4 else ""
        b.caja(274, 200 + i * 86, 620, 76, f"Pieza {i + 1} · socket · núcleos · watts                          $precio{aviso}", relleno="#fff", tam=12)
    b.caja(914, 146, 342, 300, "Tu armado\n\npiezas elegidas · total\nvs presupuesto\n\nReporte de compatibilidad:\nsocket, memoria, medidas, watts\n\n[ Guardar ]  [ Vaciar ]")
    b.nota(914, 470, "Cada opción dice si calza con lo ya\nelegido antes de comprar (regla, no LLM).", hacia=(894, 560))
    b.nota(914, 530, "«Prefiero que la IA me pregunte» lleva al\nasistente de armado (Gemini entiende y explica).")
    return b.svg()


if __name__ == "__main__":
    carpeta = Path(__file__).resolve().parent
    for nombre, funcion in (("01-asistente.svg", asistente), ("02-observabilidad.svg", observabilidad), ("03-armador.svg", armador)):
        (carpeta / nombre).write_text(funcion())
        print("ok", carpeta / nombre)
