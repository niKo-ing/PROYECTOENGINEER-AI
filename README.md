# SoloTodo AI

Base de infraestructura para un monolito modular. El backend usa FastAPI y SQLAlchemy; el frontend usa Next.js, React, TypeScript y Tailwind CSS. PostgreSQL en Supabase es la base de datos objetivo.

## Arquitectura actual

```text
frontend/ (Next.js) → backend FastAPI → SQLAlchemy → PostgreSQL (Supabase)
```

El backend mantiene `routers/`, `services/`, `repositories/`, `schemas/`, `models/` y `core/`. La autenticación se realiza con tokens de Supabase Auth y los perfiles se almacenan con SQLAlchemy, separados de las credenciales. El catálogo separa la identidad del producto de sus ofertas: `Category → Product → StoreOffer → PriceHistory`, con especificaciones flexibles, tiendas, contratos de ingesta y matching determinista. El AI Engine usa Gemini por defecto mediante un adapter configurable y un registro cerrado de tools para catálogo y perfil; también conserva el adapter OpenAI. No incorpora RAG, pgvector ni recomendaciones.

## Migraciones

`create_all` se conserva temporalmente para compatibilidad de primera ejecución. Los cambios de esquema deben aplicarse mediante Alembic, no con creación automática de tablas existentes:

```bash
alembic revision --autogenerate -m "describe el cambio"
alembic upgrade head
```

Antes de desplegar el catálogo sobre una base ya creada, genere y revise una migración que convierta productos y precios heredados en categorías y ofertas. El backend no ejecuta esa transformación automáticamente al iniciar.

## Configuración de Supabase

```bash
cp .env.example .env
```

Configure **una** de estas opciones, sin versionar `.env`:

- `DATABASE_URL`: URL completa de SQLAlchemy, recomendada para Supabase.
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` y `POSTGRES_DB`: el backend construye la URL si `DATABASE_URL` está vacío.

Obtenga host, puerto, usuario, contraseña y nombre de base desde **Supabase Dashboard → Connect**. Use el host/puerto del pooler cuando Supabase lo indique. Sin esas credenciales, el backend usa SQLite local exclusivamente para desarrollo y pruebas; Docker requiere una configuración PostgreSQL/Supabase válida.

Para habilitar `POST /api/v1/ai/chat`, defina `GEMINI_API_KEY` y `GEMINI_MODEL` en `.env` con `LLM_PROVIDER=gemini`. El endpoint permanece inactivo con estado `503` mientras falte una de esas variables. Para cambiar de proveedor, use `LLM_PROVIDER=openai` y configure las variables OpenAI correspondientes.

## Backend local

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/uvicorn app.main:app --reload
```

La documentación interactiva queda disponible en `http://localhost:8000/docs`.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

El Compose levanta únicamente el backend. PostgreSQL permanece en Supabase y Redis no se agrega todavía.

## Frontend local

```bash
cd frontend
pnpm install
pnpm dev
```

El frontend mínimo inicia en `http://localhost:3000`. No contiene todavía catálogo, autenticación, perfil, chatbot ni recomendaciones.

## Pruebas

```bash
.venv/bin/pytest -q
```
