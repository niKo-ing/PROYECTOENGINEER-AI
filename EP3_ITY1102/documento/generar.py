"""Arma EP3_ITY1102.html con las cifras reales (metrics.json y resultados de Locust) y lo imprime a PDF con Chromium."""
import csv, json, html
from pathlib import Path

R = Path(__file__).resolve().parent.parent
m = json.loads((R / "modelo/metrics.json").read_text())

def stats(name):
    rows = {r["Name"]: r for r in csv.DictReader(open(R / f"pruebas/resultados/{name}_stats.csv"))}
    return rows

def fila(label, name, key="Aggregated"):
    r = stats(name)[key]
    return f"<tr><td>{label}</td><td>{r['Request Count']}</td><td>{r['Failure Count']}</td><td>{float(r['Requests/s']):.0f}</td><td>{r['50%']}</td><td>{r['95%']}</td><td>{r['99%']}</td></tr>"

t, b = m["prueba"], m["linea_base"]
cand = "".join(f"<tr><td>{k}</td><td><code>{html.escape(json.dumps(v['mejores_hiperparametros']))}</code></td><td>{v['f1_validacion_cruzada']:.3f}</td></tr>" for k, v in m["candidatos"].items())
kinds = "".join(f"<tr><td>{k}</td><td>{v['n']}</td><td>{v['aciertos']*100:.0f} %</td></tr>" for k, v in m["por_tipo_de_par"].items())
thr = "".join(f"<tr><td>{r['umbral']}</td><td>{r['precision']}</td><td>{r['cobertura_de_positivos']}</td></tr>" for r in m["tabla_de_umbrales"])
imp = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in list(m["importancia_caracteristicas"].items())[:6])
c = t["confusion"]; ds = m["dataset"]

page = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>EP3 · TodoBarato AI</title>
<style>
@page {{ size: A4; margin: 18mm 16mm }}
body {{ font: 10.5pt/1.45 'Noto Sans', 'DejaVu Sans', sans-serif; color:#15171c }}
h1 {{ font-size: 22pt; margin: 0 0 4pt }} h2 {{ font-size: 14pt; border-bottom: 1.5px solid #2f5bea; padding-bottom: 2pt; margin: 18pt 0 6pt; page-break-after: avoid }}
h3 {{ font-size: 11pt; margin: 10pt 0 3pt; page-break-after: avoid }} p {{ margin: 4pt 0 }} code {{ font-size: 9pt; background:#f0f2f6; padding: 0 2pt }}
table {{ border-collapse: collapse; width: 100%; font-size: 9pt; margin: 6pt 0 }} th,td {{ border: 1px solid #cfd4dc; padding: 3pt 5pt; text-align: left }} th {{ background:#eef1f7 }}
img {{ max-width: 100%; }} .fig {{ text-align:center; font-size: 8.5pt; color:#555; margin: 6pt 0; page-break-inside: avoid }} .pb {{ page-break-before: always }}
.nota {{ border-left: 3px solid #b7791f; background:#fdf6e7; padding: 4pt 8pt; margin: 6pt 0; page-break-inside: avoid }}
.portada {{ margin-top: 60mm }} .mut {{ color:#667085 }}
</style></head><body>

<div class="portada"><h1>TodoBarato AI — Despliegue y optimización de un modelo de emparejamiento de productos</h1>
<p><b>Evaluación Parcial 3 · ITY1102 Arquitectura de Sistemas de Inteligencia Artificial</b></p>
<p>Equipo 1 · Repositorio: github.com/niKo-ing/PROYECTOENGINEER-AI (rama <code>ep3-modelo-aws</code>)</p>
<p class="mut">Nomenclatura de entrega: EP3_Equipo1_Apellidos.pdf</p></div>

<h2 class="pb">1. Resumen</h2>
<p>TodoBarato AI compara precios de productos tecnológicos entre tiendas chilenas. Su problema técnico central es decidir si dos
títulos de tiendas distintas describen <b>el mismo producto</b> (por ejemplo «Galaxy A54 128 GB Negro» y «Celular Samsung A54 5G 128GB»):
un error aquí mezcla precios de productos distintos y la recomendación pierde valor. En la EP1 y la EP2 se diseñó y desplegó la arquitectura base
y un agente LangGraph; en esta entrega se agrega y se pone a operar un <b>modelo propio de clasificación</b> (Random Forest, scikit-learn)
con su contenedor, API REST segura, comunicación asíncrona con RabbitMQ, dashboard interactivo, pruebas y un script de despliegue en AWS.</p>
<p>Además se unificó el chat de IA y el agente en un <b>único asistente</b> (<code>/chat</code>) y se limpió el repositorio.</p>
<div class="nota"><b>Estado del despliegue en AWS.</b> El sistema está <b>desplegado y medido en AWS Academy</b> (EC2 t3.medium, us-east-1) con <code>EP3_ITY1102/infra/desplegar.sh</code>:
dashboard <code>http://3.91.93.197/api/v1/ml/dashboard</code>, Swagger <code>http://3.91.93.197/docs</code> (IP vigente al medir; el laboratorio cambia la IP al reiniciarse y la instancia se recrea con el script).
<b>SageMaker no pudo usarse</b>: <code>CreateModel</code> fue denegado por política IAM del laboratorio (evidencia en la sección 6).</div>

<h2>2. Caso empresarial y arquitectura</h2>
<p><b>Decisión que apoya:</b> qué ofertas se agrupan bajo un mismo producto para calcular el mejor precio y el historial. Hoy el emparejador determinista
(<code>app/catalog/matching.py</code>) usa GTIN, MPN y marca+modelo; cuando la tienda no los publica el resultado queda «ambiguo» y se derivaba a un LLM. El modelo propio
resuelve esa zona gris con costo y latencia mucho menores y con una explicación auditable.</p>
<div class="fig"><img src="../diagramas/png/01-arquitectura.png"><br>Figura 1. Arquitectura de componentes.</div>
<table><tr><th>Componente</th><th>Tecnología</th><th>Por qué</th></tr>
<tr><td>API REST</td><td>FastAPI + OpenAPI (<code>/docs</code>)</td><td>Contrato documentado automáticamente, validación con Pydantic</td></tr>
<tr><td>Modelo</td><td>scikit-learn Random Forest, contenedor propio con contrato <code>/ping</code> + <code>/invocations</code></td><td>Mismo contenedor sirve en SageMaker o EC2; tabular + poco dato: un bosque supera a una red neuronal</td></tr>
<tr><td>Mensajería</td><td>RabbitMQ (cola durable, ack manual, DLQ)</td><td>Desacopla la ingesta del cómputo del modelo; Amazon MQ y SQS están bloqueados en el laboratorio</td></tr>
<tr><td>Asistente</td><td>LangGraph + Gemini</td><td>Plan priorizado, herramientas, memoria (corto y largo plazo)</td></tr>
<tr><td>Dashboard</td><td>HTML servido por la API (<code>/api/v1/ml/dashboard</code>)</td><td>Sin Node en el servidor; un solo despliegue</td></tr></table>

<h2 class="pb">3. Modelo de IA: datos, entrenamiento y métricas</h2>
<h3>3.1 Datos</h3>
<p>Se ingestaron <b>{ds['productos']} productos reales</b> de Paris (notebooks, celulares y accesorios) con los conectores del proyecto. Con ellos se generan
<b>{ds['pares']} pares etiquetados</b> ({ds['entrenamiento']} entrenamiento, {ds['prueba']} prueba, partición <i>por producto</i> para que ningún producto aparezca en ambos lados):
positivos = el mismo título reescrito como lo haría otra tienda (sin marca, palabras en otro orden, abreviaturas, relleno comercial, erratas y datos faltantes);
negativos difíciles = misma marca con otro modelo, <b>otra capacidad o RAM</b> y <b>otro color</b> (en el catálogo cada color es una oferta distinta); negativos fáciles = productos al azar.</p>
<div class="nota"><b>Limitación honesta.</b> Los pares positivos se sintetizan a partir de un solo comercio; no son pares reales entre dos tiendas, y los negativos de variante salen del mismo generador.
Una primera versión sin ruido dio F1 = 1,00, señal de un examen circular; se agregó ruido realista y la métrica bajó a un valor creíble. La validación definitiva requiere pares reales entre tiendas
(la tabla <code>ai_match_decisions</code> acumula decisiones auditables para etiquetarlos).</div>
<h3>3.2 Características e interpretabilidad</h3>
<p>12 características calculadas solo del texto (similitud de secuencia, Jaccard de palabras, marca, código de modelo, números y <b>capacidades en conflicto</b>, color, largo, palabras extra).
Cada predicción devuelve las <b>razones</b> en lenguaje natural (p. ej. «las capacidades (GB/TB) son distintas: es otra variante»), útil para auditar la decisión.</p>
<table><tr><th>Característica</th><th>Importancia</th></tr>{imp}</table>
<h3>3.3 Entrenamiento e hiperparámetros</h3>
<p>Búsqueda en malla con validación cruzada agrupada por producto (5 pliegues, métrica F1). Semilla fija ({ds['semilla']}).</p>
<table><tr><th>Modelo</th><th>Mejores hiperparámetros</th><th>F1 (CV)</th></tr>{cand}</table>
<p>Modelo elegido: <b>{m['modelo_elegido']}</b>.</p>
<h3>3.4 Resultados en el conjunto de prueba</h3>
<table><tr><th></th><th>Accuracy</th><th>Precision</th><th>Recall</th><th>F1</th><th>ROC AUC</th></tr>
<tr><td><b>Random Forest</b></td><td>{t['accuracy']}</td><td>{t['precision']}</td><td>{t['recall']}</td><td><b>{t['f1']}</b></td><td>{t['roc_auc']}</td></tr>
<tr><td>Línea base ({html.escape(b['regla'])})</td><td>{b['accuracy']}</td><td>{b['precision']}</td><td>{b['recall']}</td><td>{b['f1']}</td><td>{b['roc_auc']}</td></tr></table>
<p>Matriz de confusión: TN = {c['tn']}, FP = {c['fp']}, FN = {c['fn']}, TP = {c['tp']}. El modelo mejora la línea base en precisión (+{(t['precision']-b['precision'])*100:.0f} pp) y F1 (+{(t['f1']-b['f1'])*100:.1f} pp);
la regla simple tiene más recall pero a costa de muchos falsos positivos (mezclar productos distintos), el error más caro para el negocio.</p>
<table><tr><th>Tipo de par</th><th>n</th><th>Aciertos</th></tr>{kinds}</table>
<p><b>Punto débil:</b> las variantes cuando una tienda omite la capacidad en el título; es la principal oportunidad de mejora (sección 7).</p>
<h3>3.5 Umbral de decisión</h3>
<p>La decisión es <code>match</code> si P ≥ 0,70, <code>no_match</code> si P ≤ 0,35 y <code>ambiguous</code> entre ambos (se deja a revisión, igual que el emparejador determinista).
El 0,70 se eligió con esta tabla: precisión ≈ 0,94 conservando ≈ 82 % de los positivos.</p>
<table><tr><th>Umbral</th><th>Precisión</th><th>Cobertura de positivos</th></tr>{thr}</table>

<h2 class="pb">4. Integración de servicios y seguridad</h2>
<div class="fig"><img src="../diagramas/png/02-secuencia-asincrona.png" style="max-height:105mm"><br>Figura 2. Diagrama de secuencia del flujo asíncrono.</div>
<table><tr><th>Endpoint</th><th>Descripción</th></tr>
<tr><td><code>POST /api/v1/ml/match</code></td><td>Decisión síncrona (decision, probability, reasons, model_version)</td></tr>
<tr><td><code>POST /api/v1/ml/match/async</code></td><td>Encola el par en RabbitMQ y responde 202 con el <code>request_id</code></td></tr>
<tr><td><code>GET /api/v1/ml/decisions</code></td><td>Últimas decisiones guardadas y profundidad de la cola</td></tr>
<tr><td><code>GET /api/v1/ml/metrics · /health</code></td><td>Métricas del modelo y estado (públicos)</td></tr>
<tr><td><code>POST /api/v1/agent/run</code></td><td>Asistente unificado (chat + agente), con tarjetas de producto y traza</td></tr></table>
<p><b>Seguridad.</b> Autenticación con JWT de Supabase o llave de API (<code>X-API-Key</code>, comparación en tiempo constante); <b>límite de tasa</b> por llamador con ventana deslizante (429 + <code>Retry-After</code>);
validación estricta de entradas (422); TLS terminado en el borde (CloudFront/ALB) y puertos internos (RabbitMQ, modelo) sin exponer en el grupo de seguridad (solo TCP 80).
<b>Resiliencia.</b> Mensajes persistentes con ack manual; tras 3 fallos pasan a la cola <code>.dlq</code>; el cliente del modelo traduce fallos a 503.</p>
<p><b>Interoperabilidad.</b> La API consume el modelo por HTTP (<code>MATCH_MODEL_URL</code>), así el mismo código funciona contra el contenedor local, EC2 o un endpoint de SageMaker.</p>

<h2>5. Pruebas y calidad</h2>
<h3>5.1 Pruebas automatizadas</h3>
<p>La suite completa tiene <b>939 pruebas (todas pasan)</b>; 20 son nuevas de esta entrega (<code>tests/modelo_ml/</code>): normalización, conflicto de capacidad, de color y de código de modelo,
decisión del modelo en 3 escenarios con razones, lote, autenticación (401), validación (422), límite de tasa (429) y su ventana, flujo cola → modelo → base de datos, cola de cartas muertas y endpoints públicos.</p>
<h3>5.2 Pruebas de carga (Locust, 70 % match / 20 % métricas / 10 % async)</h3>
<table><tr><th>Escenario (local, Docker)</th><th>Peticiones</th><th>Fallos</th><th>req/s</th><th>p50 ms</th><th>p95 ms</th><th>p99 ms</th></tr>
{fila('20 usuarios · <b>antes</b> de la corrección', 'local_antes_fix')}
{fila('20 usuarios · después', 'local')}
{fila('10 usuarios', 'local_u10')}
{fila('50 usuarios', 'local_u50')}
{fila('100 usuarios', 'local_u100')}
{fila('100 usuarios · API con 4 workers', 'w4_u100')}
<tr><td colspan="7"><b>AWS (EC2 t3.medium, carga desde otro continente: incluye ≈ 250 ms de red)</b></td></tr>
{fila('20 usuarios', 'aws_u20')}
{fila('50 usuarios', 'aws_u50')}
{fila('100 usuarios', 'aws_u100')}</table>
<p><b>Hallazgo.</b> La primera corrida mostró <b>44 errores 500 (11,4 %) en <code>/ml/match/async</code></b>: <code>pika.BlockingConnection</code> no es seguro entre hilos y FastAPI atiende en un pool de hilos
(<code>StreamLostError … pop from an empty deque</code>). Se serializó el acceso al canal con un candado, se agregó reconexión y declaración única de colas: con la misma carga, <b>0 fallos en 3 870 peticiones</b>.</p>
<div class="nota"><b>Cómo leer las cifras.</b> Las filas locales son una línea base: el generador y los servicios compartían un computador con otras tareas (hasta un <code>/ping</code> trivial midió pocas decenas de req/s) y subir la API a 4 workers no cambió el rendimiento.
Las filas de <b>AWS</b> son la medición válida de capacidad: la latencia incluye ≈ 250 ms de ida y vuelta entre Chile y us-east-1 (p50 de 280 ms con 20 usuarios), y el rendimiento sube con los usuarios (≈ 39 → 80 → 102 req/s) con <b>0 fallos</b>.
<b>CloudWatch</b> registró, durante la carga, CPU media 54,9 % y máxima 77,2 % en la t3.medium: cerca del límite, por lo que <b>~100 req/s</b> es la capacidad práctica de una instancia (la alarma al 80 % no se alcanzó) y el siguiente paso es escalar horizontalmente (ASG + ALB, diseñado en la EP2).
Una primera corrida de 20 usuarios mostró 216 errores «conexión rechazada» durante los 5 s iniciales: coincidieron con el reinicio del backend del arranque, no con la carga (se repitió sin fallos; la corrida inicial se conserva como <code>aws_u20_arranque</code>).</div>
<p><b>Límite de tasa en AWS.</b> 800 peticiones con una sola llave (límite 600/min) dieron <b>547 × 200 y 253 × 429</b>. Al preparar esta prueba se detectó que el límite confiaba en <code>X-Forwarded-For</code>, que un cliente directo puede falsificar para evadirlo;
se corrigió para limitar por identidad del llamador (usuario o llave) y hay una prueba que lo verifica.</p>
<h3>5.3 Latencia del modelo aislado</h3>
<p>Un par: ≈ 5 ms; lote de 64 pares: ≈ 11 ms (0,17 ms/par). El procesamiento por lotes es la optimización más barata para la ingesta masiva.</p>

<h2 class="pb">6. Plataforma AIaaS y costos</h2>
<p><b>SageMaker (plan A).</b> Se diseñó el modelo con el contrato de SageMaker (<code>/ping</code>, <code>/invocations</code>, artefacto en <code>/opt/ml/model</code>). En la cuenta del laboratorio las cuotas permiten
<code>ml.m5.large</code> (30 endpoints), pero el intento real falló: <code>sagemaker:CreateModel</code> → <b>AccessDeniedException</b> («no identity-based policy allows the sagemaker:CreateModel action») y no existe un rol de ejecución utilizable
(<code>evidencia/sagemaker-intento.txt</code>, generado por <code>infra/intentar_sagemaker.sh</code>). <b>Plan B (el que se despliega):</b> el mismo contenedor en EC2 con Docker Compose, que migra a SageMaker sin cambios de código al contar con un rol.</p>
<table><tr><th>Opción</th><th>Costo aprox.*</th><th>Escalado</th><th>Flexibilidad</th></tr>
<tr><td>EC2 t3.medium + Docker (desplegado)</td><td>≈ USD 0,04/h (≈ 30/mes)</td><td>ASG + ALB (diseñado en EP2)</td><td>Alta: cualquier contenedor</td></tr>
<tr><td>SageMaker ml.m5.large (tiempo real)</td><td>≈ USD 0,12/h (≈ 85/mes)</td><td>Auto-scaling gestionado</td><td>Media: contrato fijo, monitoreo integrado</td></tr>
<tr><td>SageMaker Serverless Inference</td><td>por invocación</td><td>Automático (con arranque en frío)</td><td>Media</td></tr></table>
<p class="mut">*Precios de lista aproximados (us-east-1, on-demand); verificar en la calculadora de AWS antes de decidir. Para una carga baja e intermitente como esta, la opción serverless o EC2 pequeño es la económica; SageMaker en tiempo real se justifica cuando se necesita escalado y monitoreo gestionados.</p>
<div class="fig"><img src="../diagramas/png/03-despliegue-aws.png" style="max-height:80mm"><br>Figura 3. Despliegue en AWS Academy.</div>

<h2>7. Oportunidades de optimización</h2>
<ul><li><b>Variantes sin capacidad en el título</b> (67 % de aciertos): enriquecer con las especificaciones de la ficha y entrenar con pares reales entre tiendas.</li>
<li><b>Lotes:</b> el endpoint ya acepta hasta 64 pares; usarlo desde la ingesta reduce la latencia por par ≈ 30 veces.</li>
<li><b>Escalado horizontal:</b> el worker es sin estado; se escala agregando consumidores sobre la misma cola.</li>
<li><b>Cache de pares repetidos</b> y <b>reentrenamiento programado</b> con las decisiones auditadas de <code>ai_match_decisions</code> (mejora continua).</li>
<li><b>Asistente unificado:</b> chat y agente comparten una sola ruta de ejecución; la investigación web y la evidencia RAG del chat antiguo quedan como herramientas por migrar.</li></ul>

<h2 class="pb">8. Despliegue y evidencias</h2>
<p><b>Reproducir:</b> <code>bash EP3_ITY1102/infra/desplegar.sh</code> (S3 + EC2 + alarma CloudWatch, ≈ 6 min) · <code>bash EP3_ITY1102/pruebas/cargar.sh http://&lt;IP&gt; aws 50 60</code> · <code>bash EP3_ITY1102/infra/destruir.sh</code>.</p>
<div class="fig"><img src="../evidencia/dashboard-aws.png" style="max-height:140mm"><br>Figura 4. Dashboard interactivo servido desde EC2 en AWS.</div>
<table><tr><th>Evidencia</th><th>Estado</th></tr>
<tr><td>Dashboard, API y Swagger en AWS (<code>evidencia/dashboard-aws.png</code>, <code>swagger-aws.png</code>)</td><td>Hecho</td></tr>
<tr><td>Flujo API → RabbitMQ → worker → modelo → BD en AWS (decisiones guardadas, cola en 0)</td><td>Hecho</td></tr>
<tr><td>Prueba de carga remota (CSV/HTML en <code>pruebas/resultados/aws_*</code>) y métricas CloudWatch (<code>evidencia/cloudwatch.txt</code>)</td><td>Hecho</td></tr>
<tr><td>Límite de tasa (429) y autenticación (401) verificados en AWS</td><td>Hecho</td></tr>
<tr><td>Endpoint SageMaker</td><td>Intentado; denegado por IAM del laboratorio</td></tr>
<tr><td>Auto-scaling</td><td>No desplegado (una instancia); diseñado en EP2. Se mide la saturación (CPU 77 % a ≈ 100 req/s)</td></tr></table>

<h2>9. Conclusiones</h2>
<p>Se entregó un modelo propio, interpretable y medible, integrado a un servicio con API segura, mensajería asíncrona, dashboard y pruebas; la prueba de carga encontró y permitió corregir un defecto real de concurrencia, y la revisión de seguridad otro (límite de tasa evadible).
Los límites quedan explícitos: datos sintéticos de una sola tienda sin validación con pares reales, una sola instancia sin auto-scaling y SageMaker bloqueado por el laboratorio.</p>

<h2>Referencias (APA)</h2>
<p>Breiman, L. (2001). Random forests. <i>Machine Learning, 45</i>(1), 5–32. https://doi.org/10.1023/A:1010933404324</p>
<p>Pedregosa, F., Varoquaux, G., Gramfort, A., Michel, V., Thirion, B., Grisel, O., … Duchesnay, É. (2011). Scikit-learn: Machine learning in Python. <i>Journal of Machine Learning Research, 12</i>, 2825–2830.</p>
<p>Amazon Web Services. (2025). <i>Amazon SageMaker developer guide: Use your own inference code with hosting services</i>. https://docs.aws.amazon.com/sagemaker/</p>
<p>Ramírez, S. (2025). <i>FastAPI documentation</i>. https://fastapi.tiangolo.com/</p>

<h2>Declaración de uso de IA</h2>
<p>Se utilizó Claude (Anthropic) como asistente de programación para generar y revisar código, pruebas, scripts y la redacción de este informe. El equipo definió el problema, revisó los resultados,
ejecutó los experimentos y es responsable del contenido. Las cifras provienen de ejecuciones reales (<code>metrics.json</code> y los CSV de Locust del repositorio).</p>
</body></html>"""
out = R / "documento/EP3_ITY1102.html"
out.write_text(page)
print("ok", out)
