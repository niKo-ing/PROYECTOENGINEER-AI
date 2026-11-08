"""Capacidad y costo de TodoBarato AI en servidores propios con GPU (on-premise), en CLP.

Escenarios:
  * EP2: carga de la EP2 (1.200 sesiones/día, 1.500 consultas de IA/día).
  * 10K: 10.000 usuarios activos al día (meta del profe).
  * 10K simultáneos: 10.000 personas conectadas a la vez (para mostrar el límite).
Ejecutar:  python costos_servidor_propio.py
Precios consultados el 08-11-2026 (fuentes en INFORME_SERVIDOR_IA.md).
"""

import math

USD = 975          # CLP por dólar (Emol, 3-6 nov 2026: $970-980)
KWH = 280          # CLP por kWh con IVA (BT1 2026: ~240 a ~328 según distribuidora)
MESES_VIDA = 36    # el hardware se paga (deprecia) en 3 años

# ---------------- Supuestos técnicos
PAGINAS_POR_SESION, LLAMADAS_API_POR_PAGINA = 8, 3
FACTOR_PICO = 6                       # la hora pico concentra ~6x el promedio
LLM_LLAMADAS_POR_CHAT = 3
TOKENS_ENTRADA, TOKENS_SALIDA = 2_500, 400
TOK_S_POR_USUARIO = 50                # velocidad de respuesta cómoda para leer
TOK_S_POR_GPU = 1_500                 # salida total de una RTX 5090 con vLLM y un modelo 8B (medir con benchmark)
RPS_POR_SERVIDOR = 150                # catálogo con caché en un tarro de 24 núcleos (EP2 midió 22 req/s por t3.small)
ACIERTO_CACHE = 0.8                   # Cloudflare + Redis responden 8 de cada 10 lecturas del catálogo


def carga(nombre, sesiones_dia, chats_dia, rps_pico=None, streams=None):
    if rps_pico is None:
        rps_pico = sesiones_dia * PAGINAS_POR_SESION * LLAMADAS_API_POR_PAGINA / 86_400 * FACTOR_PICO
    llamadas_s = chats_dia * LLM_LLAMADAS_POR_CHAT / 86_400 * FACTOR_PICO
    duracion = TOKENS_SALIDA / TOK_S_POR_USUARIO + 0.5          # segundos por respuesta
    if streams is None:
        streams = llamadas_s * duracion                          # ley de Little: concurrencia = tasa x duración
    tok_s = streams * TOK_S_POR_USUARIO
    gpus = max(1, math.ceil(tok_s / TOK_S_POR_GPU))
    servidores_web = max(1, math.ceil(rps_pico * (1 - ACIERTO_CACHE) / RPS_POR_SERVIDOR))
    return dict(nombre=nombre, rps=rps_pico, streams=streams, tok_s=tok_s, gpus=gpus,
                web=servidores_web, chats_dia=chats_dia)


ESCENARIOS = [
    carga("EP2 (1.200 sesiones/día)", 1_200, 1_500),
    carga("10.000 usuarios activos al día", 10_000, 10_000),
    # 10.000 conectados a la vez: 1 página cada 20 s; 1 de cada 10 esperando una respuesta de la IA
    carga("10.000 usuarios SIMULTÁNEOS", 0, 0, rps_pico=10_000 / 20 * LLAMADAS_API_POR_PAGINA, streams=1_000),
]

# ---------------- Hardware: (compra CLP, watts promedio, factor clima, horas de técnico/mes)
TARRO = {
    "PC workstation Ultra 9 285K, 192 GB RAM, RTX 5090 32 GB (Paris.cl)": 9_617_520,
    "2 SSD NVMe 2 TB extra para RAID 1": 400_000,
    "UPS online 1,5 kVA": 550_000,
}
OPCIONES = {
    "A. 1 tarro RTX 5090": dict(compra=TARRO, n=1, watts=300, clima=1.0, tecnico=8, internet=92_000, extras={}),
    "C. 2 tarros RTX 5090 (alta disponibilidad, recomendado para 10.000)": dict(
        compra=TARRO, n=2, watts=380, clima=1.0, tecnico=16, internet=92_000 + 30_000,
        extras={"Switch 2.5 GbE + cableado": 250_000},
    ),
}
DOMINIO_RESPALDO_CF = 6_000 + 5 * USD   # dominio .cl, respaldo externo y Cloudflare Load Balancing (USD 5)
HORA_TECNICO = 15_000
REPUESTOS_ANUAL = 0.05

# ---------------- Nube (EP2) para comparar
AWS_EP2_USD = 120.44
GEMINI_USD_POR_CHAT = LLM_LLAMADAS_POR_CHAT * (TOKENS_ENTRADA * 0.10 + TOKENS_SALIDA * 0.40) / 1e6


def clp(v: float) -> str:
    return f"${v:,.0f}".replace(",", ".")


def costo(o):
    compra = sum(o["compra"].values()) * o["n"] + sum(o["extras"].values())
    mensual = {
        f"Depreciación ({MESES_VIDA} meses)": compra / MESES_VIDA,
        f"Electricidad ({o['n']} x {o['watts']} W promedio)": o["n"] * o["watts"] * o["clima"] * 730 / 1000 * KWH,
        "Internet fibra empresa IP fija" + (" + enlace de respaldo" if o["n"] > 1 else ""): o["internet"],
        f"Técnico ({o['tecnico']} h/mes)": o["tecnico"] * HORA_TECNICO,
        "Repuestos (5 %/año)": compra * REPUESTOS_ANUAL / 12,
        "Dominio + respaldo externo + Cloudflare": DOMINIO_RESPALDO_CF,
    }
    return compra, mensual


if __name__ == "__main__":
    print("== Capacidad necesaria (hora pico)")
    for e in ESCENARIOS:
        print(f"   {e['nombre']:<34} catálogo {e['rps']:7.1f} req/s · IA {e['streams']:6.0f} respuestas a la vez "
              f"· {e['tok_s']:7.0f} tok/s → {e['gpus']:>2} GPU RTX 5090 · {e['web']} servidor(es) web")
    print()

    for nombre, o in OPCIONES.items():
        compra, mensual = costo(o)
        total = sum(mensual.values())
        print(f"== {nombre}")
        print(f"   {'Inversión inicial':<60} {clp(compra):>13}")
        for k, v in mensual.items():
            print(f"   {k:<60} {clp(v):>13}")
        print(f"   {'COSTO MENSUAL':<60} {clp(total):>13}  (~USD {total / USD:,.0f})")
        print(f"   {'Costo a 3 años':<60} {clp(total * 36):>13}\n")

    print("== Nube (AWS + Gemini) para comparar")
    for e in ESCENARIOS[:2]:
        # 10.000 usuarios: 2 réplicas t3.small más y RDS un tamaño mayor (~USD 50)
        aws = AWS_EP2_USD + (50 if e["chats_dia"] > 1_500 else 0)
        gem = GEMINI_USD_POR_CHAT * e["chats_dia"] * 30
        print(f"   {e['nombre']:<34} AWS ~USD {aws:,.0f} + Gemini USD {gem:,.0f} = {clp((aws + gem) * USD)}/mes")

    sim = ESCENARIOS[2]
    print(f"\n10.000 SIMULTÁNEOS necesitaría ~{sim['gpus']} GPU RTX 5090 (~{sim['gpus']} tarros, "
          f"~{clp(sim['gpus'] * sum(TARRO.values()))}): un tarro no alcanza; ahí conviene la API.")
