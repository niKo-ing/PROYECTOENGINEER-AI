#!/usr/bin/env bash
# Guion de la demo en vivo con curl.   Uso:  BASE=https://xxxx.cloudfront.net KEY=<llave> bash EP3_ITY1102/api-pruebas/comandos.sh
BASE=${BASE:-http://localhost:8000}; KEY=${KEY:-clave-local}
J=(-H "content-type: application/json" -H "x-api-key: $KEY")
paso() { printf '\n\033[1m# %s\033[0m\n' "$1"; }
paso "1. Salud y métricas del modelo (públicas)"
curl -s "$BASE/api/v1/ml/health"; echo; curl -s "$BASE/api/v1/ml/metrics" | python3 -c "import json,sys;m=json.load(sys.stdin);print('modelo',m['modelo_elegido'],'F1',m['prueba']['f1'],'línea base',m['linea_base']['f1'])"
paso "2. Sin llave → 401"
curl -s -o /dev/null -w "%{http_code}\n" -XPOST "$BASE/api/v1/ml/match" -H "content-type: application/json" -d '{"a":"xx","b":"yy"}'
paso "3. Mismo producto, títulos distintos → match + razones"
curl -s -XPOST "$BASE/api/v1/ml/match" "${J[@]}" -d '{"a":"Samsung Galaxy A54 128GB Negro","b":"Celular Galaxy A54 5G 128 GB Negro"}'; echo
paso "4. Otra capacidad → no_match (la razón lo explica)"
curl -s -XPOST "$BASE/api/v1/ml/match" "${J[@]}" -d '{"a":"Apple iPhone 13 128GB Negro","b":"Apple iPhone 13 256GB Negro"}'; echo
paso "5. Entrada inválida → 422"
curl -s -o /dev/null -w "%{http_code}\n" -XPOST "$BASE/api/v1/ml/match" "${J[@]}" -d '{"a":"x"}'
paso "6. Flujo asíncrono: API → RabbitMQ → worker → modelo → base de datos"
curl -s -XPOST "$BASE/api/v1/ml/match/async" "${J[@]}" -d '{"a":"Xiaomi Redmi Note 15 Pro 256GB Azul","b":"Xiaomi Redmi Note 15 Pro 256GB Verde"}'; echo
sleep 3; curl -s "$BASE/api/v1/ml/decisions?limit=2" "${J[@]}" | python3 -m json.tool | head -20
paso "7. Dashboard:  $BASE/api/v1/ml/dashboard   ·   Swagger:  $BASE/docs"
