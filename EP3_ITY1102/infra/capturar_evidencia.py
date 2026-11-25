"""Capturas de la pila desplegada con una franja que deja a la vista la URL, la hora (UTC) y la instancia que respondió.

    python EP3_ITY1102/infra/capturar_evidencia.py https://xxxx.cloudfront.net [carpeta de salida]

Toma el dashboard del modelo y Swagger con Chromium sin interfaz y guarda /health (que en AWS informa la instancia y la
zona). Sirve como evidencia de que lo capturado viene de AWS y no de una copia local: la página del dashboard es la
misma en local y en EC2, así que sin la URL dos capturas pueden ser idénticas byte a byte.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PAGINAS = {"aws-dashboard.png": "/api/v1/ml/dashboard", "aws-swagger.png": "/docs"}


def navegador() -> str:
    for nombre in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        if ruta := shutil.which(nombre):
            return ruta
    sys.exit("No encontré Chromium ni Chrome en el PATH.")


def fuente(tamano: int) -> ImageFont.ImageFont:
    for nombre in ("DejaVuSans.ttf", "NotoSans-Regular.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(nombre, tamano)
        except OSError:
            continue
    return ImageFont.load_default(size=tamano)


def con_franja(captura: Path, destino: Path, texto: str) -> None:
    imagen = Image.open(captura).convert("RGB")
    alto = 44
    lienzo = Image.new("RGB", (imagen.width, imagen.height + alto), "#15171c")
    lienzo.paste(imagen, (0, alto))
    ImageDraw.Draw(lienzo).text((16, 12), texto, fill="#ffffff", font=fuente(17))
    lienzo.save(destino, optimize=True)


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    base = sys.argv[1].rstrip("/")
    salida = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "evidencia"
    salida.mkdir(parents=True, exist_ok=True)

    with urllib.request.urlopen(f"{base}/health", timeout=20) as respuesta:
        salud = json.loads(respuesta.read())
    (salida / "aws-health.json").write_text(json.dumps(salud, indent=2, ensure_ascii=False) + "\n")
    instancia = " · ".join(str(salud[k]) for k in ("instancia", "zona") if salud.get(k)) or "instancia sin informar"
    hora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    chromium = navegador()
    with tempfile.TemporaryDirectory() as tmp:
        for archivo, ruta in PAGINAS.items():
            bruta = Path(tmp) / archivo
            subprocess.run([chromium, "--headless=new", "--hide-scrollbars", "--window-size=1200,1500", "--virtual-time-budget=8000",
                            f"--screenshot={bruta}", f"{base}{ruta}"], check=True, capture_output=True, timeout=120)
            con_franja(bruta, salida / archivo, f"{base}{ruta}   ·   {hora}   ·   {instancia}")
            print("✔", salida / archivo)
    print("✔", salida / "aws-health.json", "→", instancia)


if __name__ == "__main__":
    main()
