"""Estimación de capacidad y costo mensual de TodoBarato AI (us-east-1, precios on-demand de lista, USD).

Los precios unitarios se copian a AWS Pricing Calculator para el enlace del documento; este script
deja la cuenta reproducible:  python3 EP2_ITY1102/infra/costos.py
"""

HORAS_MES = 730

# ---------------- Supuestos de carga (escenario de lanzamiento, 12 meses)
USUARIOS_MES = 5_000
SESIONES_DIA = 1_200
PAGINAS_POR_SESION = 8
LLAMADAS_API_POR_PAGINA = 3
FACTOR_PICO = 6               # la hora pico concentra ~6x el promedio (tarde-noche)
CHATS_DIA = 1_500             # consultas al asistente / agente
LLM_LLAMADAS_POR_CHAT = 3     # plan + herramienta + redacción (AI_MAX_TOOL_CALLS = 3)
TOKENS_ENTRADA = 2_500        # contexto RAG (≤ 1.600) + instrucciones + historial
TOKENS_SALIDA = 400
P_GEMINI_IN, P_GEMINI_OUT = 0.10, 0.40   # USD por millón de tokens (Gemini Flash-Lite, lista)

req_dia = SESIONES_DIA * PAGINAS_POR_SESION * LLAMADAS_API_POR_PAGINA
rps_medio = req_dia / 86_400
rps_pico = rps_medio * FACTOR_PICO
chats_pico_min = CHATS_DIA / (24 * 60) * FACTOR_PICO

# Capacidad por réplica (2 workers uvicorn, t3.small), MEDIDA el 25-10-2026 con prueba_carga.sh contra el ALB:
# catálogo 43,9 req/s con 2 réplicas y 20 clientes concurrentes, p95 0,95 s, 0 errores → ~22 req/s por réplica.
# El chat es I/O (espera al LLM 2-6 s): limita la concurrencia, no la CPU.
RPS_POR_REPLICA = 22
replicas_necesarias = max(2, -(-rps_pico * 2 // RPS_POR_REPLICA))  # x2 de holgura y mínimo 2 por alta disponibilidad

tok_in_mes = CHATS_DIA * 30 * LLM_LLAMADAS_POR_CHAT * TOKENS_ENTRADA
tok_out_mes = CHATS_DIA * 30 * LLM_LLAMADAS_POR_CHAT * TOKENS_SALIDA
costo_llm = tok_in_mes / 1e6 * P_GEMINI_IN + tok_out_mes / 1e6 * P_GEMINI_OUT

# ---------------- Precios unitarios (us-east-1)
EC2_T3_SMALL = 0.0208
RDS_T4G_MICRO = 0.016          # single-AZ; Multi-AZ = x2
RDS_GP3_GB = 0.115             # por GB-mes (Multi-AZ = x2)
ALB_HORA, ALB_LCU = 0.0225, 0.008
IPV4_HORA = 0.005
CW_DASHBOARD, CW_ALARMA, CW_METRICA_DETALLADA = 3.00, 0.10, 0.30
S3_GB = 0.023
DATOS_SALIDA_GB = 0.09
GPU_G5_XLARGE = 1.006          # A10G 24 GB: alternativa de modelo propio (descartada)

lineas = [
    ("ALB (1 balanceador + ~2 LCU)", ALB_HORA * HORAS_MES + 2 * ALB_LCU * HORAS_MES),
    ("EC2 API: 2 x t3.small (escala a 4 en pico)", 2 * EC2_T3_SMALL * HORAS_MES),
    ("EC2 worker de ingesta: 1 x t3.small", EC2_T3_SMALL * HORAS_MES),
    ("RDS PostgreSQL db.t4g.micro Multi-AZ", 2 * RDS_T4G_MICRO * HORAS_MES),
    ("RDS almacenamiento gp3 20 GB (x2 Multi-AZ)", 2 * 20 * RDS_GP3_GB),
    ("IPv4 públicas (3 EC2 + 2 del ALB)", 5 * IPV4_HORA * HORAS_MES),
    ("CloudWatch: dashboard + 5 alarmas + métricas detalladas", CW_DASHBOARD + 5 * CW_ALARMA + 3 * 7 * CW_METRICA_DETALLADA),
    ("S3 (5 GB: imágenes, logs, respaldos)", 5 * S3_GB),
    ("Transferencia de salida (20 GB)", 20 * DATOS_SALIDA_GB),
    ("SNS + EventBridge (< 1.000 eventos)", 0.0),
]
infra = sum(v for _, v in lineas)

if __name__ == "__main__":
    print(f"Solicitudes/día: {req_dia:,.0f} · media {rps_medio:.2f} req/s · pico {rps_pico:.1f} req/s")
    print(f"Chats en el minuto pico: {chats_pico_min:.1f} · réplicas de API necesarias: {replicas_necesarias:.0f}")
    print(f"Tokens/mes: {tok_in_mes/1e6:.1f} M entrada, {tok_out_mes/1e6:.1f} M salida → LLM ≈ USD {costo_llm:.2f}")
    print()
    for nombre, v in lineas:
        print(f"  {nombre:<58} {v:8.2f}")
    print(f"  {'Infraestructura AWS':<58} {infra:8.2f}")
    print(f"  {'Gemini Flash-Lite (API)':<58} {costo_llm:8.2f}")
    print(f"  {'TOTAL mensual':<58} {infra + costo_llm:8.2f}")
    print()
    print(f"Alternativa descartada: modelo propio en g5.xlarge 24x7 = USD {GPU_G5_XLARGE * HORAS_MES:.2f}/mes solo en GPU")
    lab = ALB_HORA + 0.008 + 3 * EC2_T3_SMALL + RDS_T4G_MICRO + 5 * IPV4_HORA
    print(f"Laboratorio (AWS Academy, RDS single-AZ): ≈ USD {lab:.3f}/hora")
