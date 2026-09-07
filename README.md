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

## CI / CD (GitHub Actions)

El repositorio tiene **CI en todos los PR/pushes** y un **CD que publica la imagen del backend en GitHub Container Registry (GHCR)** y deja listo (no ejecutado) el despliegue productivo.

### Eventos que activan cada pipeline

| Pipeline | Archivo | Se dispara con |
|---|---|---|
| CI Backend | `.github/workflows/backend.yml` | push/PR a `master` o `main` (solo `app/`, `scripts/`, `tests/`, `pyproject.toml`) → `pytest -q` |
| CI Frontend | `.github/workflows/frontend.yml` | push/PR a `master` o `main` (solo `frontend/`) → `eslint` + `next build` |
| CD Backend | `.github/workflows/cd.yml` | push a `main` **o** creación de tag `v*` (ej. `v1.2.3`) |

> [!NOTE]
> El CD está filtrado a la rama `main` según lo solicitado. Si la rama principal del repo se llama `master`, agrega `master` a `branches:` en `.github/workflows/cd.yml` (y considera renombrar la rama con `git branch -m main`).

### Imagen publicada

- Nombre: `ghcr.io/<owner>/<repository>/backend` (GHCR exige minúsculas; el workflow la calcula con `${GITHUB_REPOSITORY,,}`).
- Ejemplo para este repo: `ghcr.io/niko-ing/proyectoengineer-ai/backend`.
- Etiquetas (resolución de `docker/metadata-action@v5`):

| Evento | Etiquetas |
|---|---|
| push a `main` | `sha-<7>`, `main`, `latest` |
| tag `v1.2.3` | `sha-<7>`, `v1.2.3`, `1.2.3` |
| cualquier push CD | `sha-<7>` (imagen inmutable para rollback) |

`latest` **solo** cuando el evento es push a `main` (no en tags).

### Flujo del CD (`.github/workflows/cd.yml`)

```text
push main / tag v*
   │
   ├─ backend-tests   (pytest)
   ├─ frontend-check  (eslint + next build)
   │        │
   │        ▼
   │  build-and-publish  → docker build → push a GHCR (GITHUB_TOKEN, packages: write)
   │        │
   │        ▼
   │  deploy            → verifica imagen sha-<7> + smoke test /health
   │                     → si hay host+secretos: pull, alembic upgrade head, run, health
   │                     → si NO: reporta qué falta y NO simula un despliegue
```

Gates de despliegue: `deploy` depende de `build-and-publish`, que a su vez depende de los tests y del lint/build del frontend. Si cualquiera falla, **no se publica ni se despliega**. Además, el job `deploy` usa `concurrency` para que nunca haya dos despliegues simultáneos.

### Variables y secretos para activar el despliegue productivo

Configurables en GitHub → Settings → Secrets and variables → Actions:

| Tipo | Nombre | Uso |
|---|---|---|
| Variable | `DEPLOY_HOST` | Host del servidor (IP/DNS) |
| Variable | `DEPLOY_USER` | Usuario SSH |
| Variable | `DEPLOY_PATH` | Ruta de trabajo en el host |
| Secret | `DEPLOY_SSH_KEY` | Llave privada SSH (nunca se imprime) |
| Secret | `DATABASE_URL` | Cadena PostgreSQL/Supabase |
| Secret | `SUPABASE_URL` | URL del proyecto Supabase |
| Secret | `SUPABASE_ANON_KEY` | Anon key de Supabase |
| Secret | `LLM_PROVIDER` | `gemini` / `openai` |
| Secret | `GEMINI_API_KEY` | (u otra credencial equivalente) |

También se requieren los mismos secrets que usa CI hoy para el build del frontend: `NEXT_PUBLIC_SUPABASE_URL` y `NEXT_PUBLIC_SUPABASE_ANON_KEY`.

**Nunca** se agregan secretos reales al repositorio ni se imprimen en los logs (se pasan por `env` y se escriben en archivos temporales con máscara de ejecución).

### CI implementado vs. publicación en GHCR vs. despliegue productivo

- **CI implementado (funciona hoy):** `pytest` del backend y lint/build del frontend. Es lo único que se ejecuta en cada PR/push.
- **Publicación en GHCR (funciona hoy):** el CD construye la imagen del backend y la sube etiquetada. Se puede verificar con `docker pull`.
- **Despliegue productivo (NO activo):** el job `deploy` verifica e instala la imagen **solo cuando** existan `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_PATH` y `DEPLOY_SSH_KEY`, `DATABASE_URL`. El repositorio no tiene un proveedor de hosting configurado, así que hoy el job reporta el estado pendiente y **no simula** un despliegue exitoso.

### Ejecutar y verificar el workflow

1. Hacer push a `main` o crear un tag:
   ```bash
   git checkout main
   git push origin main
   git tag v0.1.0 && git push origin v0.1.0
   ```
2. Abrir **Actions** en GitHub y verificar el run `CD - Publicar imagen y preparar despliegue` (jobs verde, imagen publicada, smoke test OK, estado del deploy).
3. Verificar la imagen publicada localmente:
   ```bash
   echo "$GITHUB_TOKEN" | docker login ghcr.io -u <usuario> --password-stdin
   docker pull ghcr.io/niko-ing/proyectoengineer-ai/backend:latest
   docker run -d -p 8000:8000 -e DATABASE_URL=sqlite:////tmp/check.db ghcr.io/niko-ing/proyectoengineer-ai/backend:latest
   curl http://localhost:8000/health   # {"status":"ok"}
   ```
   (Ocultar el token; para tokens de máquina se necesitan los scopes `read:packages`.)

### Rollback

Cada imagen publicada queda inmutable con la etiqueta `sha-<sha del commit>`:

1. Buscar el SHA del commit bueno y su tag:
   ```bash
   git log --oneline -10
   docker image inspect ghcr.io/niko-ing/proyectoengineer-ai/backend:sha-<sha>   # ejemplo: sha-869e678
   ```
2. En el host de despliegue, volver a ejecutar el deploy con esa imagen (pull + migraciones + restart):
   ```bash
   docker pull ghcr.io/niko-ing/proyectoengineer-ai/backend:sha-<sha>
   # revisar si la migración reciente necesita downgrade antes de levantar:
   # docker run --rm -e DATABASE_URL=$DATABASE_URL IMG sh -c "alembic downgrade -1"
   docker rm -f todobarato-backend
   docker run -d --name todobarato-backend --restart unless-stopped -p 8000:8000 \
     --env-file .deploy-env ghcr.io/niko-ing/proyectoengineer-ai/backend:sha-<sha>
   curl http://localhost:8000/health   # {"status":"ok"}
   ```
3. Como alternativa a los comandos manuales, redirigir el CD a la rama/tag anterior y volver a correr el workflow desde la UI de Actions (botón **Re-run** sobre el commit deseado).

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
