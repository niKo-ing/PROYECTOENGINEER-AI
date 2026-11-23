"""Guías de compatibilidad: fuente **interna** del RAG del armador y contenido de la página /guias.

Cada guía se indexa en la base de conocimiento (``KnowledgeStore``) partida en fragmentos con embedding; el agente las
consulta con ``search_compatibility_guide`` y el asistente las cita al explicar un armado. Son textos propios escritos
a partir de las fichas de AMD, Intel, JEDEC y los fabricantes de fuentes y gabinetes.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

GUIDE_DOMAIN = "guias.todobarato.local"
GUIDE_DOC_TYPE = "guia_compatibilidad"


@dataclass(frozen=True)
class Guide:
    slug: str
    title: str
    summary: str
    body: str

    @property
    def url(self) -> str:
        return f"https://{GUIDE_DOMAIN}/{self.slug}"


GUIDES: tuple[Guide, ...] = (
    Guide(
        "socket-y-chipset",
        "Socket y chipset: qué procesador va en qué placa",
        "El socket del procesador y el de la placa madre deben ser iguales; el chipset define qué se puede hacer con la placa.",
        """## El socket manda
El socket es el zócalo donde se instala el procesador. Si el procesador y la placa madre no tienen el mismo socket, no hay forma de usarlos juntos.

- **AM4** (AMD): Ryzen 1000 a 5000 (por ejemplo Ryzen 5 5600, Ryzen 7 5700X, Ryzen 5 5600G). Usa solo memoria **DDR4**.
- **AM5** (AMD): Ryzen 7000, 8000 y 9000 (Ryzen 5 7600, Ryzen 7 7800X3D, Ryzen 5 9600X). Usa solo memoria **DDR5**. AMD promete soporte de varias generaciones, por lo que deja un camino de mejora.
- **LGA1700** (Intel): Core de 12.ª, 13.ª y 14.ª generación (Core i5-12400F, i5-13400F, i5-14600K). Admite DDR4 o DDR5, pero **cada placa trae solo uno de los dos**.
- **LGA1851** (Intel): Core Ultra 200S (Core Ultra 5 245K). Solo DDR5.
- **LGA1200** (Intel): Core de 10.ª y 11.ª generación. **LGA1151**: Core de 8.ª y 9.ª generación con chipset serie 300.

## Chipset: entrada, media y alta
- **Entrada** (A520, A620, H610): suficientes para procesadores de 65 W. Con procesadores de alto consumo (los «K» de Intel o los Ryzen 9) sus reguladores de voltaje (VRM) se calientan y el procesador baja su rendimiento.
- **Media** (B550, B650, B760, B860): la opción equilibrada; más ranuras M.2 y de RAM, mejores VRM.
- **Alta** (X670, Z790, Z890): permiten overclock del procesador en Intel (los modelos con «K») y suman conectividad.

## BIOS
Una placa fabricada antes que el procesador puede necesitar una actualización de BIOS para reconocerlo. Muchas placas modernas permiten actualizarla sin procesador (BIOS Flashback).""",
    ),
    Guide(
        "memoria-ram",
        "Memoria RAM: DDR4, DDR5, capacidad y doble canal",
        "DDR4 y DDR5 no son intercambiables; dos módulos iguales rinden más que uno; 16 GB es el mínimo razonable para jugar.",
        """## DDR4 y DDR5 no se mezclan
Los módulos DDR4 y DDR5 tienen la muesca en otra posición: físicamente no entran en la ranura del otro tipo. La placa madre define cuál se usa (AM5 y LGA1851 solo DDR5; AM4 solo DDR4; LGA1700 depende de la placa).

## Capacidad recomendada por uso
- **8 GB**: solo para tareas muy básicas; hoy se queda corto.
- **16 GB**: mínimo razonable para jugar, estudiar y trabajar con varias aplicaciones.
- **32 GB**: edición de video, programación con contenedores o máquinas virtuales, juegos en 1440p con muchas cosas abiertas.
- **64 GB**: renders 3D pesados, IA local o edición en 4K.

## Doble canal
Dos módulos iguales (por ejemplo 2×8 GB) trabajan en doble canal y entregan casi el doble de ancho de banda que uno solo. Se nota sobre todo con gráficos integrados. Conviene comprar **un kit** con la capacidad total en vez de juntar módulos distintos.

## Velocidad, XMP y EXPO
La RAM viene configurada a una velocidad base; para llegar a la anunciada (por ejemplo DDR5-6000) hay que activar el perfil **XMP** (Intel) o **EXPO** (AMD) en la BIOS. Si la placa o el procesador admiten menos velocidad, la memoria funciona igual, más lento. En AM5, DDR5-6000 es el punto ideal; en AM4, DDR4-3200 o 3600.""",
    ),
    Guide(
        "fuente-de-poder",
        "Fuente de poder: cuántos watts necesita tu equipo",
        "Suma el consumo del procesador, la tarjeta gráfica y unos 60 W del resto, y deja alrededor de 30 % de margen.",
        """## Cómo estimar el consumo
1. Consumo máximo del procesador (no solo el TDP: un Core i7-14700K puede pasar los 250 W; un Ryzen 5 7600 llega a unos 88 W).
2. Consumo de la tarjeta gráfica (por ejemplo una RTX 4060 usa unos 115 W; una RX 7800 XT unos 263 W).
3. Unos **60 W** para placa, memoria, discos y ventiladores.

Al total se le suma un **margen de 30 %**: la fuente trabaja más fresca, más silenciosa y aguanta los picos breves de la tarjeta. Además, conviene no bajar de la **fuente recomendada por el fabricante de la tarjeta**.

## Señales de una fuente insuficiente
Apagones al jugar o al renderizar, reinicios bajo carga y pantallazos azules. Una fuente justa puede funcionar, pero envejece más rápido.

## Eficiencia y formato
- La certificación **80 Plus** (Bronze, Gold, Platinum) indica cuánta energía se pierde en calor. Gold es un buen equilibrio.
- **ATX** es el tamaño normal; **SFX** es la fuente pequeña que exigen muchos gabinetes Mini-ITX. Una ATX no entra en un gabinete que solo acepta SFX.
- Las tarjetas nuevas pueden usar el conector **12V-2x6 (12VHPWR)**; las fuentes ATX 3.0/3.1 lo traen de fábrica.""",
    ),
    Guide(
        "gabinete-y-formatos",
        "Gabinete y formatos: que todo quepa",
        "La placa debe ser de un formato que el gabinete acepte, y la tarjeta y el disipador no pueden superar las medidas máximas.",
        """## Formatos de placa
- **ATX**: la placa completa, con más ranuras.
- **Micro-ATX (mATX)**: más corta; entra en gabinetes ATX y mATX.
- **Mini-ITX (ITX)**: muy pequeña; entra en casi cualquier gabinete, y es la única opción en los gabinetes compactos.

Un gabinete ATX acepta placas ATX, mATX e ITX. Uno mATX no acepta una ATX.

## Medidas que hay que revisar
- **Largo máximo de la tarjeta gráfica** (por ejemplo 360 mm). Las tarjetas de gama alta superan con facilidad los 300 mm.
- **Altura máxima del disipador** de aire (por ejemplo 157 mm). Torres como la Noctua NH-D15 miden unos 165 mm.
- **Radiadores** compatibles para refrigeración líquida (120, 240, 280 o 360 mm) y dónde se montan.
- **Formato de fuente**: ATX o SFX.

## Flujo de aire
Un frontal con malla y al menos dos ventiladores de entrada mantiene bajas las temperaturas de la tarjeta y del procesador.""",
    ),
    Guide(
        "refrigeracion",
        "Refrigeración del procesador",
        "Algunos procesadores traen disipador y otros no; el disipador debe soportar el socket, el consumo y caber en el gabinete.",
        """## ¿Trae disipador?
- Traen disipador de fábrica: Ryzen 5 5600, 5600G, 7600, 8600G, Ryzen 7 7700, y los Intel sin «K» (Core i3-12100F, i5-12400F, i5-13400F).
- **No traen**: Ryzen 7 5700X, Ryzen 5 9600X, Ryzen 7 7800X3D, Ryzen 9 7900X, Core i5-14600K, i7-14700K, Core Ultra 5 245K. Sin disipador el equipo se apaga a los segundos de encender.

## Elegir un disipador
1. **Socket**: el disipador debe traer anclaje para el socket (AM4, AM5, LGA1700, LGA1851). Los anclajes de AM4 y AM5 son compatibles entre sí.
2. **Capacidad**: su capacidad de disipación debe ser igual o mayor que el TDP del procesador; si no, el procesador baja su frecuencia por temperatura.
3. **Altura** (aire) o **radiador** (líquida): debe caber en el gabinete.

## Aire o líquida
Un buen disipador de torre con un ventilador de 120 mm enfría casi cualquier procesador de gama media. La refrigeración líquida (AIO) ayuda con procesadores de más de 150 W o en gabinetes donde una torre alta no cabe.""",
    ),
    Guide(
        "tarjeta-grafica",
        "Tarjeta gráfica: memoria de video, resolución y cuello de botella",
        "La tarjeta define el rendimiento en juegos; la memoria de video depende de la resolución, y el procesador no debe quedarse atrás.",
        """## ¿Hace falta tarjeta gráfica?
Los procesadores Intel con **F** (Core i5-12400F) y muchos Ryzen sin **G** (Ryzen 5 5600, Ryzen 7 5700X) **no tienen gráficos integrados**: sin tarjeta, el equipo no da imagen. Los Ryzen 7000/9000 traen un gráfico integrado básico, suficiente para oficina. El Ryzen 5 8600G (Radeon 760M) permite juegos livianos sin tarjeta.

## Memoria de video (VRAM) por resolución
- **1080p**: 8 GB.
- **1440p**: 12 GB.
- **4K, edición pesada o IA local**: 16 GB o más.

## Cuello de botella
Si la tarjeta es mucho más potente que el procesador, en juegos el procesador limita los FPS y parte del dinero de la tarjeta se desperdicia. Lo contrario pasa en juegos competitivos a muchos FPS, donde el procesador pesa más. El equilibrio depende del uso.

## PCIe
Las tarjetas PCIe 4.0 o 5.0 funcionan en ranuras PCIe 3.0; la diferencia de rendimiento es pequeña salvo en tarjetas de 8 carriles muy exigidas.""",
    ),
    Guide(
        "almacenamiento",
        "Almacenamiento: NVMe, SATA y disco duro",
        "Un SSD NVMe para el sistema y los juegos; un disco duro solo para guardar archivos grandes.",
        """## Tipos
- **SSD NVMe M.2**: el más rápido (3.000 a 7.000 MB/s). Va en una ranura M.2 de la placa.
- **SSD SATA 2,5"**: unos 500 MB/s; sirve para revivir un equipo antiguo.
- **Disco duro (HDD)**: 150 a 250 MB/s; barato por gigabyte, pero lento para el sistema operativo.

## Compatibilidad
- Cada placa tiene un número de ranuras M.2: no se pueden instalar más unidades NVMe que ranuras.
- Las ranuras M.2 pueden ser NVMe, SATA o ambas: revisa el manual de la placa.
- Un NVMe PCIe 4.0 funciona en una ranura PCIe 3.0, más lento.

## Capacidad
500 GB alcanza para oficina; para juegos, 1 TB es lo mínimo cómodo (un juego actual pesa entre 50 y 150 GB); para edición de video, 2 TB o más.""",
    ),
    Guide(
        "presupuesto-por-uso",
        "Cómo repartir el presupuesto según el uso",
        "En juegos, la tarjeta gráfica se lleva la mayor parte; en trabajo, el procesador y la RAM; en oficina, basta un procesador con gráficos integrados.",
        """## Juegos
La tarjeta gráfica debería llevarse entre el 35 % y el 50 % del presupuesto. Un procesador de 6 núcleos moderno (Ryzen 5 7600, Core i5-12400F) acompaña bien a tarjetas de gama media.

## Oficina y estudio
Un procesador con gráficos integrados (Core i5-12400, Ryzen 5 5600G), 16 GB de RAM en doble canal y un SSD NVMe. No hace falta tarjeta gráfica.

## Programación
El procesador (más núcleos acortan las compilaciones) y 32 GB de RAM si usas Docker o máquinas virtuales.

## Edición de video, 3D e IA local
Procesador de 8 o más núcleos, 32 GB de RAM o más, y una tarjeta con suficiente memoria de video (12–16 GB). El almacenamiento rápido y grande acelera el trabajo con proyectos pesados.

## Pensar en mejoras futuras
Una plataforma actual (AM5, por ejemplo) permite cambiar solo el procesador en unos años. Una fuente con margen permite subir de tarjeta sin cambiarla.""",
    ),
    Guide(
        "mejorar-mi-pc",
        "Mejorar el PC que ya tienes",
        "El orden que suele rendir más: SSD, RAM, tarjeta gráfica (revisando la fuente) y, al final, procesador o plataforma.",
        """## Orden recomendado
1. **SSD**: si el sistema está en un disco duro, cambiarlo por un SSD es la mejora más notoria por su precio.
2. **RAM**: pasar de 8 a 16 GB (o de un módulo a dos en doble canal).
3. **Tarjeta gráfica**: la mayor ganancia en juegos. Antes, confirma que la **fuente** tenga los watts y conectores necesarios y que la tarjeta **quepa** en el gabinete.
4. **Procesador**: si la placa lo admite, un procesador más nuevo del mismo socket (por ejemplo de Ryzen 5 3600 a Ryzen 7 5700X en AM4) suele requerir solo una actualización de BIOS.
5. **Plataforma**: cambiar procesador, placa y RAM juntos cuando el socket ya no tiene opciones.

## Cuidado con
- Fuentes antiguas o genéricas al subir de tarjeta.
- Pasar a DDR5: obliga a cambiar placa y memoria.
- Procesadores sin disipador incluido.""",
    ),
)

GUIDE_BY_SLUG = {g.slug: g for g in GUIDES}


def seed_guides(db: Session) -> int:
    """Indexa las guías en la base de conocimiento (fragmentos + embeddings). Idempotente por URL."""
    from app.ai.rag.knowledge_store import KnowledgeStore

    store = KnowledgeStore.from_settings(db)
    created = 0
    for guide in GUIDES:
        _, new = store.upsert_document(
            url=guide.url, title=guide.title, content=f"# {guide.title}\n\n{guide.summary}\n\n{guide.body}", document_type=GUIDE_DOC_TYPE,
            source_name="Guías TodoBarato", domain=GUIDE_DOMAIN, source_type="technical_document", language="es",
        )
        created += int(new)
    db.commit()
    return created


def search_guides(db: Session, query: str, k: int = 4) -> list[dict]:
    """Fragmentos de guías más relevantes (búsqueda híbrida: palabras clave + embeddings)."""
    from app.ai.rag.knowledge_store import KnowledgeStore

    store = KnowledgeStore.from_settings(db)
    hits = store.search(query, top_k=k, filters={"document_type": GUIDE_DOC_TYPE})
    if not hits:
        seed_guides(db)
        hits = store.search(query, top_k=k, filters={"document_type": GUIDE_DOC_TYPE})
    out = []
    for hit in hits:
        slug = (hit.source_url or "").rsplit("/", 1)[-1]
        guide = GUIDE_BY_SLUG.get(slug)
        out.append({"guide": slug, "title": guide.title if guide else hit.source_name, "url": f"/guias/{slug}", "content": hit.content[:900],
                    "keyword_score": hit.keyword_score, "semantic_score": hit.semantic_score})
    return out
