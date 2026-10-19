// Genera docs/agente/Presentacion_EP2_Agente_TodoBarato.pptx (apoyo visual de la exposición de 10 min).
//
//   NODE_PATH=<carpeta con node_modules/pptxgenjs> node scripts/generar_presentacion.js [ruta/apply_theme.js]
//
// La diapositiva de justificación queda para que el equipo la complete con sus palabras (la pauta
// prohíbe redactarla con IA). Las notas de cada diapositiva traen solo datos y pasos de la demo.
const path = require("path");
const pptxgen = require("pptxgenjs");

const RAIZ = path.resolve(__dirname, "..");
const IMG = path.join(RAIZ, "docs", "agente", "img");
const SALIDA = path.join(RAIZ, "docs", "agente", "Presentacion_EP2_Agente_TodoBarato.pptx");

const THEME = {
  name: "TodoBarato Agente",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1B1B1B", lt1: "FFFFFF", dk2: "14342A", lt2: "EEF5EA",
    accent1: "2C5F2D", accent2: "97BC62", accent3: "C2410C", accent4: "0E7490", accent5: "6D28D9", accent6: "B91C1C",
    hlink: "0E7490", folHlink: "6D28D9",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 pulgadas
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "Agente de ahorro de TodoBarato";
pres.author = "[Integrantes]";
const C = pres.SchemeColor;

pres.defineSlideMaster({
  title: "CONTENIDO",
  background: { color: C.background1 },
  objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.3, w: 9.0, h: 0.7, fontSize: 30, bold: true, color: C.text2, align: "left", valign: "middle", margin: 0 }, text: "" } }],
  slideNumber: { x: 9.1, y: 5.25, w: 0.5, h: 0.3, fontSize: 10, color: C.accent1 },
});
pres.defineSlideMaster({
  title: "OSCURA",
  background: { color: C.text2 },
  objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.5, w: 8.8, h: 1.4, fontSize: 40, bold: true, color: C.background1, align: "left", valign: "middle", margin: 0 }, text: "" } }],
});

let notasTotal = 0;
function diapo(maestra, seccion, notas) {
  const s = pres.addSlide({ masterName: maestra, sectionTitle: seccion });
  if (notas) { s.addNotes(notas); notasTotal++; }
  return s;
}
const sombra = () => ({ type: "outer", color: "000000", opacity: 0.12, blur: 6, offset: 2, angle: 90 });
const texto = (s, t, o) => s.addText(t, { isTextBox: true, margin: 0, fontFace: THEME.bodyFontFace, ...o });

// 1 ── portada
pres.addSection({ title: "Apertura" });
let s = diapo("OSCURA", "Apertura", "Presenta: [Integrante 1]. 20 s. Qué problema resuelve y qué verán: arquitectura, planificación, memoria y demo en vivo.");
s.addText("Agente de ahorro de TodoBarato", { placeholder: "title" });
texto(s, "Consulta, escritura y razonamiento, con memoria y replanificación", { x: 0.6, y: 3.0, w: 8.8, h: 0.5, fontSize: 20, color: C.accent2 });
texto(s, "ISY0101 Ingeniería de Soluciones con IA · Evaluación Parcial 2", { x: 0.6, y: 4.5, w: 8.8, h: 0.3, fontSize: 14, color: C.background1 });
texto(s, "[Integrante 1] · [Integrante 2]", { x: 0.6, y: 4.85, w: 8.8, h: 0.3, fontSize: 14, color: C.background1 });

// 2 ── el caso
pres.addSection({ title: "Diseño" });
s = diapo("CONTENIDO", "Diseño", "Presenta: [Integrante 1]. 60 s. Caso: asesor de compras de un comparador de precios. El agente deja registro en la base: alertas y listas.");
s.addText("Un asesor de compras que deja registro", { placeholder: "title" });
const casos = [
  ["1", "«Notebook para la universidad, hasta $400.000»", "Busca, compara tiendas, juzga el precio y guarda la lista"],
  ["2", "«Notebook gamer, hasta $300.000, avísame»", "No hay en ese precio: cambia de estrategia y deja una alerta"],
  ["3", "«Revisa mis alertas»", "Compara cada alerta con los precios de hoy"],
  ["4", "«Prefiero Samsung, no quiero Huawei»", "Lo recuerda en conversaciones futuras"],
];
casos.forEach(([n, pide, hace], i) => {
  const x = 0.5 + (i % 2) * 4.6, y = 1.3 + Math.floor(i / 2) * 1.95;
  s.addShape(pres.ShapeType.roundRect, { x, y, w: 4.4, h: 1.75, fill: { color: C.background2 }, rectRadius: 0.12, shadow: sombra(), objectName: `Tarjeta ${n}` });
  s.addShape(pres.ShapeType.ellipse, { x: x + 0.2, y: y + 0.2, w: 0.5, h: 0.5, fill: { color: C.accent1 }, objectName: `Número ${n}` });
  texto(s, n, { x: x + 0.2, y: y + 0.2, w: 0.5, h: 0.5, fontSize: 18, bold: true, color: C.background1, align: "center", valign: "middle" });
  texto(s, pide, { x: x + 0.85, y: y + 0.15, w: 3.4, h: 0.65, fontSize: 15, bold: true, color: C.text2, valign: "middle" });
  texto(s, hace, { x: x + 0.25, y: y + 0.95, w: 3.95, h: 0.65, fontSize: 14, color: C.text1, valign: "top" });
});

// 3 ── arquitectura
s = diapo("CONTENIDO", "Diseño", "Presenta: [Integrante 1]. 60 s. Recorrer de izquierda a derecha: API → AgentService → grafo LangGraph. A la derecha: Gemini, checkpointer (memoria de corto plazo), 11 herramientas y memoria de largo plazo con embeddings.");
s.addText("Orquestación de componentes", { placeholder: "title" });
s.addImage({ path: path.join(IMG, "arquitectura.png"), x: 0.5, y: 1.15, w: 9.0, h: 4.05, altText: "Diagrama de componentes: cliente, FastAPI, AgentService, grafo LangGraph, Gemini, SqliteSaver, herramientas, memoria de largo plazo, catálogo y tablas del agente" });

// 4 ── flujo
s = diapo("CONTENIDO", "Diseño", "Presenta: [Integrante 2]. 60 s. Nodos: recall → plan → act ⇄ tools → reflect. El ciclo rojo es la replanificación (máx. 2). give_up cierra las llamadas pendientes si se pasa de 10 pasos.");
s.addText("Flujo del grafo y replanificación", { placeholder: "title" });
s.addImage({ path: path.join(IMG, "flujo.png"), x: 1.1, y: 1.15, w: 7.8, h: 3.99, altText: "Flujo del grafo: recall, plan, act, tools, reflect, con ciclo de replanificación, remember y give_up" });

// 5 ── decisiones adaptativas
pres.addSection({ title: "Comportamiento" });
s = diapo("CONTENIDO", "Comportamiento", "Presenta: [Integrante 2]. 60 s. Las reglas de diagnóstico son código determinista (se prueban sin LLM). Frenos anti-bucle: máx. 2 replanificaciones y cada motivo replanifica una sola vez.");
s.addText("Cinco diagnósticos cambian el plan", { placeholder: "title" });
const cab = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.accent1 }, fontSize: 14 } });
const fila = (a, b, c) => [a, b, c].map((t, j) => ({ text: t, options: { fontSize: 13, bold: j === 1, color: j === 1 ? C.accent3 : C.text1 } }));
s.addTable(
  [
    [cab("Observación"), cab("Diagnóstico"), cab("Adaptación")],
    fila("Búsqueda con 0 resultados", "sin_resultados", "Términos más generales, sin filtro de precio"),
    fila("Todo cuesta más que el presupuesto", "sobre_presupuesto", "Gama inferior o alerta; informa cuánto falta"),
    fila("Todas las ofertas sin stock", "sin_stock", "Descarta y elige otra tienda"),
    fila("Tendencia dice «esperar»", "precio_alto", "No compra hoy; alerta al promedio histórico"),
    fila("Una herramienta falló", "error_herramienta", "Corrige parámetros y reintenta una vez"),
  ],
  { x: 0.5, y: 1.25, w: 9.0, colW: [3.2, 2.4, 3.4], rowH: 0.62, border: { type: "solid", pt: 0.75, color: "C9D6C3" }, fill: { color: C.background1 }, valign: "middle", autoPage: false, margin: [0.05, 0.1, 0.05, 0.1] },
);

// 6 ── memoria
s = diapo("CONTENIDO", "Comportamiento", "Presenta: [Integrante 1]. 60 s. Corto plazo = checkpointer del hilo (sobrevive a reinicios; Postgres con varias réplicas). Largo plazo = tabla agent_memories con embeddings. El caso clave: «Recomiéndame un celular» no comparte palabras con «Prefiero Samsung»: por eso existe la memoria núcleo.");
s.addText("Memoria de corto y largo plazo", { placeholder: "title" });
const columnas = [
  ["Corto plazo", "Continuidad dentro de una tarea", ["Historial del hilo en el checkpointer de LangGraph", "SQLite en local, Postgres con varias réplicas", "Ventana de 24 mensajes + resumen de lo recortado", "Cada hilo atado a su usuario"], C.accent1],
  ["Largo plazo", "Conocimiento entre conversaciones", ["Preferencias, hechos y episodios con embedding", "Memoria núcleo: lo importante se carga siempre", "Búsqueda semántica; sin duplicados", "Aislada por usuario"], C.accent4],
];
columnas.forEach(([t, sub, items, color], i) => {
  const x = 0.5 + i * 4.6;
  s.addShape(pres.ShapeType.roundRect, { x, y: 1.2, w: 4.4, h: 2.85, fill: { color: C.background2 }, rectRadius: 0.12, shadow: sombra(), objectName: `Columna ${t}` });
  texto(s, t, { x: x + 0.25, y: 1.3, w: 3.9, h: 0.45, fontSize: 20, bold: true, color });
  texto(s, sub, { x: x + 0.25, y: 1.75, w: 3.9, h: 0.3, fontSize: 14, italic: true, color: C.text2 });
  s.addText(items.map((t2, k) => ({ text: t2, options: { bullet: true, breakLine: k < items.length - 1 } })), { isTextBox: true, x: x + 0.25, y: 2.15, w: 3.95, h: 1.8, fontSize: 14, color: C.text1, paraSpaceAfter: 5, margin: 0, valign: "top" });
});
s.addShape(pres.ShapeType.roundRect, { x: 0.5, y: 4.3, w: 9.0, h: 0.75, fill: { color: C.text2 }, rectRadius: 0.1, objectName: "Fórmula de recuperación" });
texto(s, "puntaje = 0,75 · similitud + 0,15 · importancia/5 + 0,10 · recencia", { x: 0.7, y: 4.3, w: 8.6, h: 0.75, fontSize: 18, bold: true, color: C.background1, align: "center", valign: "middle" });

// 7 ── demo
pres.addSection({ title: "Demostración" });
s = diapo("CONTENIDO", "Demostración", "Presentan ambos. 3 min. Comando: python scripts/demo_agente.py --live --embeddings gemini (si la cuota de Gemini se agotó, usar el modo sin --live: misma traza, modelo guionado). Mostrar en cada historia: plan inicial, llamadas a herramientas, línea [reflect] con el diagnóstico y el estado final de la base.");
s.addText("Demo en vivo: cinco historias", { placeholder: "title" });
const hist = [["1", "Compra simple", "consulta → razonamiento → escritura"], ["2", "Sin resultados", "replan ×2 y alerta de precio"], ["3", "Precio inflado", "el historial dice «esperar»"], ["4", "Otro día, otro hilo", "recuerda «Prefiero Samsung»"], ["5", "Bajó el precio", "se cumple la alerta"]];
hist.forEach(([n, t, d], i) => {
  const x = 0.5 + i * 1.8;
  s.addShape(pres.ShapeType.roundRect, { x, y: 1.3, w: 1.65, h: 2.35, fill: { color: C.background2 }, rectRadius: 0.1, shadow: sombra(), objectName: `Historia ${n}` });
  s.addShape(pres.ShapeType.ellipse, { x: x + 0.55, y: 1.45, w: 0.55, h: 0.55, fill: { color: C.accent3 }, objectName: `Número historia ${n}` });
  texto(s, n, { x: x + 0.55, y: 1.45, w: 0.55, h: 0.55, fontSize: 18, bold: true, color: C.background1, align: "center", valign: "middle" });
  texto(s, t, { x: x + 0.1, y: 2.1, w: 1.45, h: 0.55, fontSize: 14, bold: true, color: C.text2, align: "center", valign: "middle" });
  texto(s, d, { x: x + 0.1, y: 2.7, w: 1.45, h: 0.85, fontSize: 12, color: C.text1, align: "center", valign: "top" });
});
s.addShape(pres.ShapeType.roundRect, { x: 0.5, y: 4.0, w: 9.0, h: 0.9, fill: { color: C.text2 }, rectRadius: 0.1, objectName: "Comando de la demo" });
texto(s, ".venv/bin/python scripts/demo_agente.py --live --embeddings gemini", { x: 0.7, y: 4.0, w: 8.6, h: 0.9, fontSize: 14, color: C.accent2, fontFace: "Courier New", align: "center", valign: "middle" });

// 8 ── evidencia
pres.addSection({ title: "Cierre" });
s = diapo("CONTENIDO", "Cierre", "Presenta: [Integrante 2]. 45 s. Cifras reales del repositorio. La demo con Gemini completó las historias 1 a 3; la cuota gratuita se agotó en la 4 y el agente lo informó sin caerse. Pruebas en vivo con Gemini y contra Postgres real: pasaron.");
s.addText("Evidencia", { placeholder: "title" });
const cifras = [["88", "pruebas del agente"], ["873", "pruebas en todo el repositorio"], ["11", "herramientas: consulta, razonamiento y escritura"], ["5", "diagnósticos que replanifican"]];
cifras.forEach(([n, t], i) => {
  const x = 0.5 + i * 2.28;
  s.addShape(pres.ShapeType.roundRect, { x, y: 1.3, w: 2.1, h: 2.2, fill: { color: C.background2 }, rectRadius: 0.1, shadow: sombra(), objectName: `Cifra ${t}` });
  texto(s, n, { x, y: 1.45, w: 2.1, h: 1.0, fontSize: 54, bold: true, color: C.accent1, align: "center", valign: "middle", fontFace: THEME.headFontFace });
  texto(s, t, { x: x + 0.15, y: 2.5, w: 1.8, h: 0.85, fontSize: 14, color: C.text1, align: "center", valign: "top" });
});
s.addText(
  [
    { text: "Gemini real: ", options: { bold: true, color: C.accent3, breakLine: false } },
    { text: "historias 1 a 3 completas, con replan por sin_resultados, sobre_presupuesto y precio_alto", options: { color: C.text1 } },
  ],
  { isTextBox: true, x: 0.5, y: 3.85, w: 9.0, h: 0.4, fontSize: 16, margin: 0 },
);
s.addText(
  [
    { text: "Checkpointer: ", options: { bold: true, color: C.accent3 } },
    { text: "dos conexiones distintas comparten un mismo hilo en Postgres 16 real", options: { color: C.text1 } },
  ],
  { isTextBox: true, x: 0.5, y: 4.35, w: 9.0, h: 0.4, fontSize: 16, margin: 0 },
);

// 9 ── justificación (la completa el equipo)
s = diapo("OSCURA", "Cierre", "A completar por el equipo: justificación técnica con sus propias palabras (la pauta no permite redactarla con IA). Presentan ambos. Preparar respuestas para la ronda de preguntas (10 min).");
s.addText("Por qué estas decisiones", { placeholder: "title" });
texto(s, "A completar por el equipo, con sus propias palabras", { x: 0.6, y: 3.0, w: 8.8, h: 0.4, fontSize: 18, bold: true, color: C.accent2 });
s.addText(
  ["LangGraph y el ciclo reflect → plan", "Reglas deterministas frente al LLM", "Checkpointer Postgres y embeddings semánticos", "Límites conocidos y siguientes pasos"].map((t, k, a) => ({ text: t, options: { bullet: true, breakLine: k < a.length - 1 } })),
  { isTextBox: true, x: 0.6, y: 3.45, w: 8.8, h: 1.6, fontSize: 16, color: C.background1, paraSpaceAfter: 4, margin: 0, valign: "top" },
);

(async () => {
  await pres.writeFile({ fileName: SALIDA });
  const aplicar = process.argv[2];
  if (aplicar) await require(aplicar).applyTheme(SALIDA, THEME);
  console.log("Presentación en", SALIDA, `(${notasTotal} diapositivas con notas)`);
})();
