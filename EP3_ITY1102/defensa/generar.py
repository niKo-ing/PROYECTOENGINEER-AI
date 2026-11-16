import json
from pathlib import Path
R = Path(__file__).resolve().parent.parent
m = json.loads((R / "modelo/metrics.json").read_text()); t, b = m["prueba"], m["linea_base"]
def slide(title, body): return f'<section><h2>{title}</h2>{body}</section>'
S = [
slide("El problema: ¿es el mismo producto?", f"""<div class="cols"><div><p>Comparar precios exige agrupar ofertas del <b>mismo</b> producto entre tiendas. Un error mezcla precios de productos distintos.</p>
<ul><li>«Galaxy A54 <b>128GB</b> Negro» = «Celular A54 5G 128 GB Negro» → mismo</li><li>«iPhone 13 <b>128GB</b>» ≠ «iPhone 13 <b>256GB</b>» → variante distinta</li></ul>
<p>El emparejador determinista (GTIN/MPN) deja casos <i>ambiguos</i>; antes se enviaban a un LLM (lento y caro).</p></div>
<div class="kpi"><b>{t['f1']*100:.1f} %</b>F1 del modelo propio<br><span>vs {b['f1']*100:.1f} % de la línea base</span></div></div>"""),
slide("Arquitectura desplegada", '<img src="../diagramas/png/01-arquitectura.png" style="max-height:5.3in"><p class="c">API REST · RabbitMQ · worker · contenedor del modelo (contrato SageMaker) · dashboard · CloudWatch</p>'),
slide("Modelo: Random Forest interpretable", f"""<div class="cols"><div><ul><li><b>60 productos reales</b> de Paris → 554 pares (partición por producto)</li><li>12 características del texto: capacidad, color, código de modelo…</li><li>Búsqueda en malla + validación cruzada agrupada (F1)</li><li>Cada decisión trae <b>razones</b> en lenguaje natural</li></ul>
<p><b>Honestidad:</b> datos sintéticos de una tienda; la primera versión dio F1 = 1,00 (examen circular) y se endureció con ruido.</p></div>
<div><table><tr><th></th><th>Prec.</th><th>Recall</th><th>F1</th></tr><tr><td>Random Forest</td><td>{t['precision']}</td><td>{t['recall']}</td><td><b>{t['f1']}</b></td></tr><tr><td>Línea base</td><td>{b['precision']}</td><td>{b['recall']}</td><td>{b['f1']}</td></tr></table>
<p class="c">Umbral 0,70 → precisión 0,94 con 82 % de cobertura</p></div></div>"""),
slide("Integración y seguridad", '<img src="../diagramas/png/02-secuencia-asincrona.png" style="max-height:4.1in"><ul class="small"><li>JWT o <code>X-API-Key</code> · límite de tasa 429 · validación 422 · TLS en el borde · puertos internos cerrados</li><li>Cola durable, ack manual, 3 reintentos → DLQ</li></ul>'),
slide("Pruebas: la carga encontró un bug real", """<div class="cols"><div><ul><li><b>939 pruebas</b> pasan (20 nuevas del modelo/API/cola)</li><li>Locust: 44 errores 500 (11,4 %) en <code>/ml/match/async</code></li><li>Causa: <code>pika</code> no es seguro entre hilos</li><li>Corrección: candado + reconexión → <b>0 fallos en 3 870 peticiones</b></li></ul></div>
<div class="kpi"><b>0 fallos</b>después de la corrección<br><span>p95 ≈ 110 ms · p99 ≈ 140 ms (20 usuarios, local)</span></div></div><p class="c">Cifras locales: línea base de comportamiento, no capacidad; la medición válida es contra EC2.</p>"""),
slide("AIaaS: SageMaker vs. EC2, costos y mejoras", """<table><tr><th>Opción</th><th>Costo aprox.</th><th>Cuándo</th></tr><tr><td>EC2 t3.medium + Docker</td><td>≈ USD 0,04/h</td><td>Carga baja/media, control total (desplegado)</td></tr><tr><td>SageMaker ml.m5.large</td><td>≈ USD 0,12/h</td><td>Auto-scaling y monitoreo gestionados</td></tr><tr><td>SageMaker Serverless</td><td>por invocación</td><td>Tráfico intermitente</td></tr></table>
<ul class="small"><li>Laboratorio: sin rol de ejecución → SageMaker bloqueado; mismo contrato <code>/invocations</code> migra sin cambios</li><li>Mejoras: pares reales entre tiendas · variantes sin capacidad (67 %) · lotes (×30) · reentrenar con decisiones auditadas</li></ul>"""),
]
html = """<!doctype html><html lang="es"><head><meta charset="utf-8"><title>EP3 Presentación</title><style>
@page { size: 13.333in 7.5in; margin: 0 }
body { margin:0; font: 20px/1.4 'Noto Sans','DejaVu Sans',sans-serif; color:#15171c }
section { width:13.333in; height:7.5in; box-sizing:border-box; padding:.55in .8in; page-break-after:always; overflow:hidden; background:#fff; position:relative }
h2 { font-size: 36px; margin:0 0 .25in; border-left: 8px solid #2f5bea; padding-left: 14px }
.cols { display:grid; grid-template-columns: 1.3fr 1fr; gap:.5in; align-items:center } ul { padding-left: 22px } li { margin: 6px 0 }
.kpi { background:#eef1f7; border-radius:16px; padding:.35in; text-align:center; font-size:20px } .kpi b { display:block; font-size:64px; color:#2f5bea } .kpi span { color:#667085; font-size:17px }
table { border-collapse:collapse; width:100%; font-size:20px } th,td { border:1px solid #cfd4dc; padding:8px 12px; text-align:left } th { background:#eef1f7 }
img { display:block; margin:0 auto } .c { text-align:center; color:#667085; font-size:17px } .small { font-size:18px } code { background:#f0f2f6; padding:0 4px; font-size:.85em }
</style></head><body>""" + "".join(S) + "</body></html>"
(R / "defensa/presentacion.html").write_text(html)
