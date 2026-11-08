"""Mide la latencia de una ruta con N clientes concurrentes (para comparar antes y después).

    python servidor_propio/medir_latencia.py http://127.0.0.1:8000/api/v1/products?query=notebook 20 15
"""

import statistics
import sys
import threading
import time

import httpx

url = sys.argv[1]
concurrencia = int(sys.argv[2]) if len(sys.argv) > 2 else 20
segundos = float(sys.argv[3]) if len(sys.argv) > 3 else 15

tiempos: list[float] = []
errores = 0
candado = threading.Lock()
fin = time.monotonic() + segundos


def cliente() -> None:
    global errores
    with httpx.Client(timeout=10) as http:
        while time.monotonic() < fin:
            inicio = time.perf_counter()
            try:
                ok = http.get(url).status_code == 200
            except httpx.HTTPError:
                ok = False
            dt = time.perf_counter() - inicio
            with candado:
                if ok:
                    tiempos.append(dt)
                else:
                    errores += 1


hilos = [threading.Thread(target=cliente) for _ in range(concurrencia)]
for h in hilos:
    h.start()
for h in hilos:
    h.join()

tiempos.sort()
p = lambda q: tiempos[min(len(tiempos) - 1, int(q * len(tiempos)))] * 1000  # noqa: E731
print(f"{len(tiempos) / segundos:7.1f} req/s · p50 {p(0.50):6.1f} ms · p95 {p(0.95):6.1f} ms · "
      f"p99 {p(0.99):6.1f} ms · promedio {statistics.mean(tiempos) * 1000:6.1f} ms · errores {errores}")
