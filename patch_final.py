from docx import Document
from docx.oxml import OxmlElement

path = "prueba 1/EP1_Arc42_SoloTodo_AI_final.docx"
doc = Document(path)


def insert_after(paragraph, text):
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    p = paragraph._parent.add_paragraph()
    p._p.getparent().remove(p._p)
    paragraph._p.addnext(p._p)
    p.text = text
    return p


def find(text):
    for p in doc.paragraphs:
        if p.text.strip() == text:
            return p
    raise ValueError(text)


# Expand section 1.2 with the quality principles requested by IE3 and IE4.
p = find("Nota de trazabilidad: El repositorio no establece SLA, latencia objetivo, disponibilidad porcentual ni presupuesto. Esos valores no se agregan aquí.")
p.text = (
    "Los principios de diseño se aplican según las capacidades comprobables del proyecto. "
    "Escalabilidad: el backend está separado del frontend mediante API y el catálogo separa "
    "productos, ofertas e historial, aunque no existe configuración productiva de autoscaling. "
    "Flexibilidad: el monolito está modularizado y el proveedor LLM se selecciona mediante "
    "configuración, con adapters para Gemini y OpenAI. Seguridad: los endpoints privados validan "
    "tokens Bearer/JWT de Supabase y la configuración sensible se obtiene desde variables de entorno. "
    "Observabilidad: existen /health, logging de ingestas y registros de estado, duración, errores y "
    "cantidades procesadas. Confiabilidad: se usan timeouts y pool_pre_ping, se manejan excepciones "
    "del scheduler y los casos ambiguos de matching no se fusionan automáticamente. El repositorio "
    "no define valores cuantitativos de SLA, latencia o disponibilidad."
)

# Add the explicit rubric sections before the existing architectural constraints.
anchor = find("2. Restricciones")
content = [
    ("1.3 Especificación de infraestructura", ""),
    ("Componentes principales de la arquitectura de IA:", ""),
    ("Datos: información de productos, categorías, ofertas por tienda, precios, historial y especificaciones. Las fuentes observadas son SP Digital y Paris mediante conectores de ingesta. PostgreSQL/Supabase almacena el catálogo y el historial.", ""),
    ("Modelo: no se entrena ni almacena un modelo propio en el repositorio. La IA se consume mediante proveedores LLM externos, Gemini u OpenAI, seleccionados por configuración. El matching utiliza primero identificadores y señales deterministas y usa IA como fallback para ambigüedades.", ""),
    ("API: backend FastAPI con API REST versionada bajo /api/v1. Expone operaciones de catálogo, perfil, IA, administración y el endpoint /health.", ""),
    ("Interfaz: frontend Next.js, React, TypeScript y Tailwind CSS, con vistas de búsqueda, categorías, productos, comparación, autenticación, chat y administración.", ""),
    ("Recursos computacionales: el procesamiento de negocio, ingesta y persistencia se ejecuta en CPU. No se requiere GPU/TPU para una inferencia local porque el proyecto utiliza proveedores LLM externos. La imagen backend observada usa python:3.14-slim; el dimensionamiento productivo exacto no está definido en el repositorio.", ""),
    ("Frameworks y servicios: FastAPI, SQLAlchemy, Alembic, Next.js, React, TypeScript, Docker y proveedores LLM Gemini/OpenAI. PostgreSQL en Supabase es la base de datos objetivo y Supabase Auth gestiona autenticación.", ""),
    ("1.4 Estrategias de integración y despliegue", ""),
    ("Integración continua implementada: GitHub Actions ejecuta pruebas pytest para backend y lint/build para frontend. Docker Compose construye el backend, aplica alembic upgrade head y ejecuta Uvicorn.", ""),
    ("Despliegue propuesto según la evidencia disponible: mantener el backend contenedorizado, el frontend como aplicación Next.js y PostgreSQL/Auth en Supabase. No se afirma un hosting productivo porque no está definido en el proyecto. Edge computing no es necesario para este caso: la IA y el catálogo dependen de datos centralizados y proveedores externos.", ""),
    ("Alternativas de integración: un monolito modular reduce complejidad operacional y es coherente con el equipo/proyecto actual; microservicios podrían aislar ingesta, catálogo e IA, pero agregarían redes, despliegue y observabilidad no presentes. Para esta entrega se conserva el monolito modular por eficiencia y mantenibilidad.", ""),
    ("Flujo CI/CD documentado: cambio de código → instalación de dependencias → pruebas backend → lint y build frontend → construcción del contenedor backend → migraciones Alembic → ejecución de Uvicorn. El repositorio implementa CI; el paso de publicación a producción queda como propuesta porque no existe workflow de CD.", ""),
    ("Referencias técnicas", ""),
    ("FastAPI. (s. f.). FastAPI documentation. https://fastapi.tiangolo.com/", ""),
    ("Docker. (s. f.). Docker documentation. https://docs.docker.com/", ""),
    ("Supabase. (s. f.). Supabase documentation. https://supabase.com/docs", ""),
    ("Declaración de uso de inteligencia artificial", ""),
    ("Se utilizó una herramienta de inteligencia artificial generativa como apoyo para organizar y redactar la documentación arc42, resumir la arquitectura existente y revisar la correspondencia entre el proyecto y la rúbrica. La información técnica fue contrastada con los archivos del repositorio; no se utilizaron datos inventados para completar la arquitectura.", ""),
]
last = anchor._p.getprevious()
for text, _ in reversed(content):
    # Insert in document order immediately before the section 2 paragraph.
    new = OxmlElement("w:p")
    anchor._p.addprevious(new)
    p = anchor._parent.add_paragraph()
    p._p.getparent().remove(p._p)
    anchor._p.addprevious(p._p)
    p.text = text

# Remove the no-longer-needed Anexo B and its following paragraphs.
start = None
for p in list(doc.paragraphs):
    if p.text.strip().startswith("Anexo B. Información que NO se encuentra"):
        start = p
        break
if start is not None:
    current = start
    while current is not None:
        nxt = current._p.getnext()
        current._element.getparent().remove(current._element)
        if nxt is None:
            break
        current = next((x for x in doc.paragraphs if x._p is nxt), None)

doc.save(path)
print(path)
