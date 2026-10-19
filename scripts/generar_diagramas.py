"""Genera los diagramas del informe (docs/agente/img/*.png) con matplotlib.

    python3 scripts/generar_diagramas.py

Los mismos diagramas están en Mermaid en docs/agente/ARQUITECTURA.md (GitHub los dibuja solo);
estos PNG existen para pegarlos en el informe en Word/PDF.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

SALIDA = Path(__file__).resolve().parents[1] / "docs" / "agente" / "img"
AZUL, VERDE, NARANJA, GRIS, ROJO, LILA = "#dbeafe", "#dcfce7", "#ffedd5", "#f3f4f6", "#fee2e2", "#ede9fe"
BORDE = "#374151"


def caja(ax, x, y, w, h, texto, color, *, tam=9, negrita=False, estilo="round,pad=0.02,rounding_size=0.08"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=estilo, fc=color, ec=BORDE, lw=1.2))
    ax.text(x + w / 2, y + h / 2, texto, ha="center", va="center", fontsize=tam, fontweight="bold" if negrita else "normal", linespacing=1.25)


def flecha(ax, a, b, *, texto="", rad=0.0, color=BORDE, estilo="-|>", dy=0.0, dx=0.0, lw=1.3):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=estilo, mutation_scale=13, lw=lw, color=color, connectionstyle=f"arc3,rad={rad}"))
    if texto:
        ax.text((a[0] + b[0]) / 2 + dx, (a[1] + b[1]) / 2 + dy, texto, fontsize=7.5, ha="center", va="center", color=color, bbox=dict(fc="white", ec="none", pad=0.6))


def lienzo(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    return fig, ax


def arquitectura():
    fig, ax = lienzo(14, 6.2)
    ax.text(7, 5.95, "Orquestación de componentes del agente de ahorro", ha="center", fontsize=12, fontweight="bold")

    caja(ax, 0.2, 2.8, 1.2, 0.8, "Cliente", GRIS, negrita=True)
    caja(ax, 1.7, 2.8, 1.6, 0.8, "FastAPI\nPOST /agent/run", AZUL)
    caja(ax, 3.6, 2.8, 1.7, 0.8, "AgentService\n(arma y traza)", AZUL)
    flecha(ax, (1.4, 3.2), (1.7, 3.2))
    flecha(ax, (3.3, 3.2), (3.6, 3.2))

    ax.add_patch(FancyBboxPatch((5.9, 1.0), 2.2, 4.2, boxstyle="round,pad=0.02,rounding_size=0.1", fc="#fefce8", ec=BORDE, lw=1.6))
    ax.text(7.0, 4.95, "Grafo LangGraph", ha="center", fontsize=10, fontweight="bold")
    for i, nombre in enumerate(["recall", "plan", "act ⇄ tools", "reflect", "remember"]):
        caja(ax, 6.25, 4.3 - i * 0.72, 1.5, 0.5, nombre, VERDE, tam=8.5)
    flecha(ax, (5.3, 3.2), (5.9, 3.2))

    caja(ax, 8.9, 4.5, 2.1, 0.8, "Gemini\nChatGoogleGenerativeAI", NARANJA, tam=8.5)
    caja(ax, 8.9, 3.3, 2.1, 0.8, "SqliteSaver\nmemoria de corto plazo", LILA, tam=8.5)
    caja(ax, 8.9, 2.0, 2.1, 0.9, "Herramientas (11)\nconsulta · razonamiento\n· escritura", VERDE, tam=8)
    caja(ax, 8.9, 0.7, 2.1, 0.9, "LongTermMemory\nrecall / add\npuntaje = sim + imp + rec", LILA, tam=8)
    flecha(ax, (8.1, 4.55), (8.9, 4.9), estilo="<|-|>")
    flecha(ax, (8.1, 3.6), (8.9, 3.7), estilo="<|-|>")
    flecha(ax, (8.1, 3.0), (8.9, 2.5))
    flecha(ax, (8.1, 1.5), (8.9, 1.15), estilo="<|-|>")

    caja(ax, 3.6, 1.2, 1.7, 0.8, "planning.py\nplan · diagnose", AZUL, tam=8)
    flecha(ax, (5.3, 1.6), (5.9, 1.6), estilo="<|-|>", color="#6b7280")
    flecha(ax, (4.45, 2.8), (4.45, 2.0), color="#6b7280", estilo="-")

    caja(ax, 11.6, 2.7, 2.2, 0.8, "Catálogo SQL\nproductos · ofertas · historial", GRIS, tam=8)
    caja(ax, 11.6, 1.6, 2.2, 0.8, "Tablas del agente\nalertas · listas de compra", GRIS, tam=8)
    caja(ax, 11.6, 0.6, 2.2, 0.8, "agent_memories\ntexto + embedding", GRIS, tam=8)
    ax.set_ylim(-0.9, 6.2)
    caja(ax, 8.9, -0.7, 2.1, 0.7, "EmbeddingProvider\nGemini o hash local", NARANJA, tam=8)
    flecha(ax, (11.0, 2.7), (11.6, 3.05), color="#6b7280")
    flecha(ax, (11.0, 2.3), (11.6, 2.0), color="#6b7280")
    flecha(ax, (11.0, 1.0), (11.6, 1.0), color="#6b7280", estilo="<|-|>")
    flecha(ax, (9.95, 0.7), (9.95, 0.0), color="#6b7280", texto="embed_text", dx=0.55)

    fig.savefig(SALIDA / "arquitectura.png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def flujo():
    fig, ax = lienzo(11.2, 5.6)
    ax.text(5.6, 5.35, "Flujo de trabajo del agente y ciclo de replanificación", ha="center", fontsize=12, fontweight="bold")
    y = 3.0
    nodos = {"start": (0.2, 0.9, "START", GRIS), "recall": (1.4, 2.0, "recall\nmemoria + presupuesto", VERDE), "plan": (3.8, 1.6, "plan\nplan priorizado", VERDE), "act": (5.9, 1.8, "act\nLLM + herramientas", NARANJA), "tools": (8.1, 1.4, "tools\nToolNode", VERDE)}
    for clave, (x, w, texto, color) in nodos.items():
        caja(ax, x, y, w, 0.8, texto, color, tam=8.5)
    orden = list(nodos)
    for a, b in zip(orden, orden[1:]):
        flecha(ax, (nodos[a][0] + nodos[a][1], y + 0.4), (nodos[b][0], y + 0.4))

    caja(ax, 9.8, 2.8, 1.2, 1.2, "reflect\ndiagnose", ROJO, tam=8.5, estilo="round,pad=0.02,rounding_size=0.4")
    flecha(ax, (9.5, y + 0.4), (9.8, y + 0.4))
    flecha(ax, (10.4, 4.0), (4.6, 3.8), rad=0.18, color="#b91c1c", texto="condiciones cambiaron  →  REPLAN  (máx. 2)", dy=0.62, dx=0.0)
    flecha(ax, (10.0, 2.8), (6.9, 3.0), rad=-0.3, color="#15803d", texto="todo bien", dy=-0.5, dx=0.2)

    caja(ax, 5.8, 1.1, 2.0, 0.8, "remember\nepisodio + preferencias", LILA, tam=8)
    caja(ax, 3.1, 1.1, 1.9, 0.8, "give_up\n(límite de pasos)", GRIS, tam=8)
    caja(ax, 8.5, 1.1, 0.9, 0.8, "END", GRIS, tam=9)
    flecha(ax, (6.8, 3.0), (6.8, 1.9), texto="responde", dx=0.5)
    flecha(ax, (6.3, 3.0), (4.4, 1.9), rad=0.15, texto="> max_steps", dx=-0.6, dy=0.2)
    flecha(ax, (5.0, 1.5), (5.8, 1.5))
    flecha(ax, (7.8, 1.5), (8.5, 1.5))

    ax.text(0.2, 0.62, "Diagnósticos que disparan un replan:", fontsize=8.5, fontweight="bold")
    ax.text(0.2, 0.02, "sin_resultados · sobre_presupuesto · sin_stock · precio_alto (veredicto «esperar») · error_herramienta\n"
            "Cada motivo replanifica una sola vez; el plan nuevo conserva los pasos ya hechos.", fontsize=8, linespacing=1.5)
    fig.savefig(SALIDA / "flujo.png", dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    SALIDA.mkdir(parents=True, exist_ok=True)
    arquitectura()
    flujo()
    print("Diagramas en", SALIDA)
