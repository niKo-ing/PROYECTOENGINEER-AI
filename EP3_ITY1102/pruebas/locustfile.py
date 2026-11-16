"""Prueba de carga de la API del modelo.

    locust -f EP3_ITY1102/pruebas/locustfile.py --headless -u 20 -r 5 -t 60s --host http://localhost:8000 \
           --csv EP3_ITY1102/pruebas/resultados/api --html EP3_ITY1102/pruebas/resultados/api.html

Las llaves van en ``ML_API_KEYS`` (separadas por coma; cada usuario virtual usa una y el límite de tasa es por llave). Mezcla realista: 70 % consulta síncrona, 20 % métricas, 10 % encolado asíncrono.
"""

import os
import random

from locust import HttpUser, between, task

KEYS = [k for k in os.getenv("ML_API_KEYS", os.getenv("ML_API_KEY", "clave-local")).split(",") if k]  # un cupo de límite de tasa por llave
PARES = [
    ("Samsung Galaxy A54 128GB Negro", "Celular Galaxy A54 5G 128 GB Negro"),
    ("Apple iPhone 13 128GB Negro", "Apple iPhone 13 256GB Negro"),
    ("Notebook Lenovo IdeaPad 3 15IAH8 8GB 512GB", "Lenovo Ideapad 3 15IAH8 512GB 8GB notebook"),
    ("Xiaomi Redmi Note 15 Pro 256GB Azul", "Smartphone Xiaomi Redmi Note 15 Pro 256 GB Verde"),
    ("Apple Macbook Air Chip M5 16GB 512GB Plata", "Macbook Air M5 16GB RAM 512GB SSD plata"),
]


class Cliente(HttpUser):
    wait_time = between(0.05, 0.3)

    def on_start(self):
        self.key = {"X-API-Key": random.choice(KEYS)}

    def par(self):
        a, b = random.choice(PARES)
        return {"a": a, "b": b}

    @task(7)
    def match(self):
        self.client.post("/api/v1/ml/match", json=self.par(), headers=self.key, name="POST /ml/match")

    @task(2)
    def metrics(self):
        self.client.get("/api/v1/ml/metrics", name="GET /ml/metrics")

    @task(1)
    def match_async(self):
        self.client.post("/api/v1/ml/match/async", json=self.par(), headers=self.key, name="POST /ml/match/async")
