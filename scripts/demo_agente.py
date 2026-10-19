"""Demo del agente de ahorro de TodoBarato: cinco historias con traza completa.

    python scripts/demo_agente.py                 # modelo guionado, sin red, determinista
    python scripts/demo_agente.py --live          # Gemini real (usa GEMINI_API_KEY de .env)
    python scripts/demo_agente.py --live --embeddings gemini   # además, memoria con embeddings reales
    python scripts/demo_agente.py --only 2        # una sola historia

Todo corre sobre un catálogo de ejemplo en SQLite en memoria; no toca su base de datos.
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import models  # noqa: E402,F401
from app.agent.demo_data import seed_demo_catalog  # noqa: E402
from app.agent.llm import AgentLLMError, get_chat_model  # noqa: E402
from app.agent.service import AgentRunResult, AgentService  # noqa: E402
from app.agent.testing import AhorroPolicy, ScriptedChatModel  # noqa: E402
from app.ai.rag.embedding import GeminiEmbeddingProvider, LocalHashEmbeddingProvider  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db import Base  # noqa: E402
from app.models.agent import AgentMemory, PriceAlert, ShoppingList  # noqa: E402
from app.models.catalog import StoreOffer  # noqa: E402

USER = "demo-cliente-1"


def titulo(texto: str) -> None:
    print("\n" + "=" * 78 + f"\n{texto}\n" + "=" * 78)


def mostrar(result: AgentRunResult) -> None:
    for e in result.trace:
        node = e["node"]
        if node == "recall":
            recuerdos = [f"«{m['content']}» (relevancia {m['relevance']})" for m in e["memories"]] or ["(nada relevante)"]
            print(f"  [recall]  presupuesto detectado: {e['budget_clp']}  |  memoria: " + "; ".join(recuerdos))
        elif node == "plan":
            etiqueta = "REPLAN por " + e["replan"] if e["replan"] else "plan inicial"
            print(f"  [plan]    {etiqueta} (fuente: {e['source']})")
            for paso in e["plan"]:
                print(f"              · {paso}")
        elif node == "act":
            llamadas = ", ".join(f"{c['tool']}({', '.join(f'{k}={v}' for k, v in c['args'].items())})" for c in e["tool_calls"]) or "responde al usuario"
            print(f"  [act {e['step']}]   {llamadas}")
        elif node == "reflect":
            if e["diagnosis"]:
                print(f"  [reflect] ⚠ {e['diagnosis']['reason']}: {e['diagnosis']['detail']}  →  {e['decision']}")
        elif node == "give_up":
            print(f"  [límite]  se alcanzó el máximo de {e['max_steps']} pasos")
        elif node == "remember":
            for guardado in e["stored"]:
                print(f"  [memoria] guardó: {guardado[:110]}")
    print("\n  RESPUESTA:\n" + textwrap.indent(textwrap.fill(result.answer, 74), "    "))
    print(f"\n  herramientas: {', '.join(result.tools_used)} | escrituras: {result.wrote or '—'} | replanificaciones: {result.replans} | pasos: {result.steps}")


def estado_bd(db) -> None:
    print("\n  ── Estado en la base de datos ──")
    for a in db.query(PriceAlert):
        print(f"  alerta #{a.id}: producto {a.product_id}, objetivo ${a.target_price_clp:,}, {'ACTIVA' if a.active else 'CUMPLIDA a $' + format(a.triggered_price_clp, ',')}".replace(",", "."))
    for s in db.query(ShoppingList):
        print(f"  lista #{s.id} «{s.name}»: total ${s.total_clp:,}".replace(",", "."))
    for m in db.query(AgentMemory):
        print(f"  memoria [{m.kind}] {m.content[:100]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="usar Gemini real en vez del modelo guionado")
    parser.add_argument("--embeddings", choices=["local", "gemini"], default="local")
    parser.add_argument("--only", type=int, choices=range(1, 6), help="ejecutar solo una historia")
    args = parser.parse_args()

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    catalogo = seed_demo_catalog(db)
    embedder = GeminiEmbeddingProvider(settings.gemini_api_key, dimensions=256) if args.embeddings == "gemini" else LocalHashEmbeddingProvider()
    saver = MemorySaver()

    def agente(consultas: list[str]) -> AgentService:
        llm = get_chat_model() if args.live else ScriptedChatModel(policy=AhorroPolicy(consultas))
        return AgentService(db, USER, llm=llm, embedder=embedder, checkpointer=saver)

    modo = "Gemini real" if args.live else "modelo guionado (sin red)"
    print(f"Agente de ahorro TodoBarato — {modo}, embeddings: {args.embeddings}")

    historias = {
        1: ("Compra simple: consulta → razonamiento → escritura", ["Lenovo"], "compra", "Quiero un notebook Lenovo para la universidad, presupuesto $400.000. Arma una lista de compra."),
        2: ("Planificación adaptativa: sin resultados y sobre presupuesto", ["notebook gamer", "notebook"], "gamer", "Quiero un notebook gamer, presupuesto $300.000. Avísame cuando baje."),
        3: ("Razonamiento sobre precios: el historial dice «esperar»", ["ASUS TUF"], "asus", "Necesito el notebook ASUS TUF, presupuesto $900.000. Guarda la lista si conviene."),
        4: ("Memoria de largo plazo entre hilos distintos", ["Samsung"], "memoria-a", "Prefiero Samsung y no quiero Huawei. Busco un celular, presupuesto $400.000."),
        5: ("Condiciones cambiantes: bajó el precio y se cumple la alerta", [], "gamer", "Revisa mis alertas de precio."),
    }
    try:
        correr(args, historias, agente, db, catalogo)
    except AgentLLMError as error:
        print(f"\n  ✖ {error}\n  (la demo se detiene aquí; lo anterior sí quedó ejecutado)")
    estado_bd(db)


def correr(args, historias, agente, db, catalogo) -> None:
    for numero, (nombre, consultas, hilo, pedido) in historias.items():
        if args.only and args.only != numero:
            continue
        titulo(f"Historia {numero}: {nombre}\n  Usuario ({hilo}): {pedido}")
        if numero == 4:
            mostrar(agente(consultas).run(pedido, hilo))
            print("\n  ··· otro día, conversación NUEVA (hilo distinto) ···")
            pedido_b = "Recomiéndame un celular."
            print(f"  Usuario (memoria-b): {pedido_b}")
            mostrar(agente(consultas).run(pedido_b, "memoria-b"))
        else:
            if numero == 5:
                print("  ··· pasan los días: Paris baja el Lenovo IdeaPad 3 de $349.990 a $289.990 ···")
                for oferta in db.query(StoreOffer).filter_by(product_id=catalogo["lenovo"]):
                    oferta.price = 289_990
                db.commit()
            mostrar(agente(consultas).run(pedido, hilo))


if __name__ == "__main__":
    main()
