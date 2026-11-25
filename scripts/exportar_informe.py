"""Exporta un informe de docs/entrega (Markdown) a PDF en formato académico: A4, Arial 11, márgenes de 2,5 y 2 cm,
diagramas Mermaid dibujados y capturas incluidas. Uso:

    .venv/bin/python scripts/exportar_informe.py docs/entrega/ISY0101-EP3.md [salida.pdf]

Los comentarios HTML del Markdown (notas internas del equipo) no aparecen en el PDF. Necesita Chromium y conexión para
cargar Mermaid desde jsDelivr (versión fija). Al final informa cuántas páginas tiene el PDF.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"
ESTILO = """
@page { size: A4; margin: 2.5cm 2cm }
body { font: 11pt/1.4 Arial, 'Liberation Sans', Helvetica, sans-serif; color: #111 }
h1 { font-size: 17pt; margin: 0 0 6pt } h2 { font-size: 13.5pt; margin: 16pt 0 6pt; page-break-after: avoid }
h3 { font-size: 12pt; margin: 12pt 0 4pt; page-break-after: avoid } p, li { margin: 4pt 0 } ul, ol { padding-left: 18pt }
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; margin: 6pt 0; page-break-inside: auto }
th, td { border: 1px solid #bbb; padding: 3pt 5pt; text-align: left; vertical-align: top } th { background: #eef1f5 }
tr { page-break-inside: avoid } code { font: 9pt 'DejaVu Sans Mono', monospace; background: #f1f3f6; padding: 0 2pt }
img { max-width: 100%; } blockquote { margin: 6pt 0; padding: 2pt 10pt; border-left: 3px solid #c9a227; background: #fbf7e8 }
.mermaid { text-align: center; margin: 8pt 0; page-break-inside: avoid } .mermaid svg { max-height: 115mm }
"""


def a_html(md_path: Path) -> str:
    texto = re.sub(r"<!--.*?-->", "", md_path.read_text(), flags=re.S)
    # Los bloques ```mermaid pasan como <div class="mermaid"> para que Mermaid los dibuje.
    texto = re.sub(r"```mermaid\n(.*?)```", lambda m: f'<div class="mermaid">\n{html.escape(m.group(1))}</div>', texto, flags=re.S)
    cuerpo = markdown.markdown(texto, extensions=["tables", "fenced_code", "sane_lists", "md_in_html"])
    titulo = html.escape(md_path.stem)
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{titulo}</title>
<base href="{md_path.parent.resolve().as_uri()}/"><style>{ESTILO}</style>
<script src="{MERMAID}"></script></head><body>{cuerpo}
<script>mermaid.initialize({{ startOnLoad: true, theme: "neutral", flowchart: {{ useMaxWidth: true }} }});</script></body></html>"""


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    origen = Path(sys.argv[1]).resolve()
    destino = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else origen.with_suffix(".pdf")
    chrome = next((c for c in ("chromium", "chromium-browser", "google-chrome") if shutil.which(c)), None) or sys.exit("Falta Chromium")
    with tempfile.TemporaryDirectory() as tmp:
        pagina = Path(tmp) / "informe.html"
        pagina.write_text(a_html(origen))
        subprocess.run([chrome, "--headless=new", "--no-pdf-header-footer", "--virtual-time-budget=20000", "--run-all-compositor-stages-before-draw",
                        f"--print-to-pdf={destino}", pagina.as_uri()], check=True, capture_output=True, timeout=180)
    paginas = subprocess.run(["pdfinfo", str(destino)], capture_output=True, text=True).stdout
    total = re.search(r"Pages:\s+(\d+)", paginas)
    print(f"{destino}: {total.group(1) if total else '?'} páginas")


if __name__ == "__main__":
    main()
