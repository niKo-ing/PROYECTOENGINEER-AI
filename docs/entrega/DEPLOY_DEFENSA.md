# Redespliegue para la defensa (ITY1102 e ISY0101)

La infraestructura de AWS se destruyó para no gastar créditos. Esta guía la levanta desde cero en **una instancia
EC2** (`desplegar.sh`) con todo lo que se muestra en las dos defensas:

| Servicio | Dirección |
|---|---|
| API, Swagger y modelo de emparejamiento | `http://IP` · `http://IP/docs` · `http://IP/api/v1/ml/dashboard` |
| Frontend: asistente, armador, Mis computadores y panel | `http://IP:3000` · `/armar/asistente` · `/mis-pc` · `/observabilidad` |

**Tiempo:** unos 15 minutos (10–12 de compilación en la instancia). Empiecen **40 minutos antes** de la defensa.
**Costo:** ~USD 0,05 por hora. Al terminar, destruyan todo (paso 6).

> La pila se probó completa en Docker el 23-11-2026, con el mismo `docker-compose.aws.yml` y el verificador del paso 5:
> 15 de 15 verificaciones en verde, desde una base vacía y con Gemini respondiendo. Lo que no se pudo probar desde aquí es
> AWS mismo, porque no hay credenciales del laboratorio.

## 0. Lo que necesitan (una vez)

* AWS CLI v2, `git`, `openssl`, `python3`, `curl` y una terminal **bash** (en fish, escriban `bash` primero).
* El repositorio en la rama con el armador:
  * hasta que se mergee el PR #15: `git switch armador-pc-observabilidad && git pull`;
  * después: `git switch master && git pull`.
* Un archivo `.env` local con `GEMINI_API_KEY` (llave de desarrollo de Google AI Studio). Está en `.gitignore`: **nunca
  se sube**.

`desplegar.sh` empaqueta el **último commit** (`git archive HEAD`): lo que no esté commiteado no se despliega.

## 1. Credenciales del laboratorio

En AWS Academy: *Learner Lab* → **Start Lab** → esperar el punto verde → **AWS Details** → *AWS CLI: Show*. Copien
el bloque en `~/.aws/credentials`, bajo `[default]`. Duran unas 4 horas.

```bash
export AWS_DEFAULT_REGION=us-east-1
aws sts get-caller-identity          # debe mostrar la cuenta del laboratorio
```

## 2. Variables de entorno

```bash
cd PROYECTOENGINEER-AI
set -a; . ./.env; set +a                         # GEMINI_API_KEY (y AUTH_JWT_SECRET si lo tienen)
export ADMIN_EMAILS="su-correo@ejemplo.cl"       # quién puede abrir /observabilidad en producción
export DEMO_EMAIL="$ADMIN_EMAILS"                # la cuenta que usarán en la demo
read -rs -p "Contraseña de la demo: " DEMO_PASSWORD; export DEMO_PASSWORD; echo
```

| Variable | Para qué | Si falta |
|---|---|---|
| `GEMINI_API_KEY` | Asistente y agente con Gemini | El asistente responde solo con reglas («Explicación automática») |
| `ADMIN_EMAILS` | Acceso al panel en producción | `/observabilidad` responde 403 a todos |
| `AUTH_JWT_SECRET` | Firma de sesiones (obligatoria en producción) | `desplegar.sh` genera una al azar |
| `DEMO_EMAIL` / `DEMO_PASSWORD` | Solo para el verificador del paso 5 | Se omiten las pruebas de cuenta, panel y asistente |

Los secretos **no** van en el repositorio ni en los datos de arranque de la instancia. `desplegar.sh` los escribe en
`EP3_ITY1102/infra/.salida/secretos.env` (ignorado por git, permisos 600) y los sube cifrados al bucket privado del
laboratorio. La instancia los descarga y **los borra del bucket** al leerlos.

## 3. (Opcional) Catálogo de productos del modelo de emparejamiento

Si tienen `ep3_data.db` en la raíz (se genera con los pasos de `EP3_ITY1102/README.md`), `desplegar.sh` la sube sola y
el dashboard del modelo muestra productos reales. Sin ella, el modelo responde igual.

El **catálogo del armador de PC** (82 piezas) se carga solo en la base SQLite de la instancia: el backend lo carga al
arrancar si la base está vacía, y `desplegar.sh` vuelve a ejecutar `seed_pc_parts` al final, que es idempotente.

## 4. Desplegar

```bash
bash EP3_ITY1102/infra/desplegar.sh
```

Imprime la IP, la URL del frontend y el comando para verificar. Las direcciones quedan en
`EP3_ITY1102/infra/.salida/estado.env` (ignorado por git).

## 5. Verificar antes de presentar

```bash
source EP3_ITY1102/infra/.salida/estado.env
bash EP3_ITY1102/infra/verificar_defensa.sh --esperar "$API" "$WEB"
```

`--esperar` reintenta hasta 20 minutos mientras la instancia compila. Debe terminar en **«Todo listo para la
defensa.»**, después de comprobar:

* **API:**
  * `/health`;
  * el modelo (`/api/v1/ml/health`);
  * el catálogo del armador con piezas;
  * Swagger.
* **Cuenta y asistente:**
  * la cuenta de la demo (si no existe, la crea);
  * el panel (confirma `ADMIN_EMAILS`);
  * el asistente: arma un PC y lo explica Gemini.
* **Frontend:**
  * `/`, `/armar`, `/armar/asistente`, `/mis-pc`, `/guias` y `/observabilidad`;
  * que carguen sus archivos;
  * que el proxy `/api/v1` llegue a la API.

**El panel parte vacío** en una base nueva. Hagan 4 o 5 consultas en `/armar/asistente` (una con «4K» muestra el
desempate entre reglas y Gemini) y una inyección («ignora tus instrucciones…»), para que aparezcan ejecuciones,
latencias y una protección. Las cifras de la evaluación (235 ejecuciones) están en `evals/resultados/` y en
`docs/entrega/capturas/`.

Para ITY1102, la prueba de carga: `source EP3_ITY1102/infra/.salida/estado.env && bash EP3_ITY1102/pruebas/cargar.sh "$API" aws 50 60`.

## 6. Al terminar (siempre)

```bash
bash EP3_ITY1102/infra/destruir.sh      # instancia, alarma, grupo de seguridad y bucket
```

## Problemas frecuentes

| Síntoma | Causa | Qué hacer |
|---|---|---|
| `ExpiredToken` o `InvalidClientTokenId` | Venció la sesión del laboratorio (4 h) | Volver a copiar las credenciales (paso 1) |
| El verificador espera 20 minutos y falla en `/health` | La instancia sigue compilando o falló el arranque | EC2 → la instancia → *Actions → Monitor → Get system log*; buscar el error de `docker compose` |
| La página se queda en «Cargando…» | Frontend en modo desarrollo | Ya está corregido (`frontend/Dockerfile` compila para producción); desplieguen el último commit |
| `/observabilidad` responde 403 | Su correo no está en `ADMIN_EMAILS` | `export ADMIN_EMAILS=…`, `destruir.sh` y `desplegar.sh` |
| Error 500 al iniciar sesión | Falta `AUTH_JWT_SECRET` | `desplegar.sh` la genera; revisen que el despliegue sea del último commit |
| «Explicación automática» en el asistente | Sin `GEMINI_API_KEY`, o cuota agotada (429) | Revisar la llave en `.env`; esperar un minuto (cuota gratuita) |
| La IP cambió | Se reinició el laboratorio | Volver a desplegar: la IP pública no es fija |

## Plan B: la misma pila en su computador

Si AWS falla el día de la defensa, la pila probada corre igual en local con Docker:

```bash
set -a; . ./.env; set +a; export ADMIN_EMAILS="su-correo@ejemplo.cl"
( umask 077; printf 'GEMINI_API_KEY=%s\nAUTH_JWT_SECRET=%s\nADMIN_EMAILS=%s\n' "$GEMINI_API_KEY" "${AUTH_JWT_SECRET:-$(openssl rand -hex 32)}" "$ADMIN_EMAILS" > EP3_ITY1102/infra/secretos.env )
cd EP3_ITY1102/infra && ML_API_KEYS=clave-local docker compose -f docker-compose.aws.yml up -d --build && cd ../..
bash EP3_ITY1102/infra/verificar_defensa.sh --esperar http://localhost http://localhost:3000
# al terminar
cd EP3_ITY1102/infra && ML_API_KEYS=x docker compose -f docker-compose.aws.yml down -v && rm -f secretos.env
```

`EP3_ITY1102/infra/secretos.env` está en `.gitignore`. Usen `localhost` y no `127.0.0.1`.

## Versión escalable (opcional, solo ITY1102)

`desplegar_asg.sh` levanta ALB, Auto Scaling 2–4, RDS y CloudFront en unos 15 minutos y ~USD 0,15 por hora. Sirve
**solo la API y el modelo**: no trae frontend, Gemini ni cuentas. Úsenla únicamente para mostrar el escalado (IE5) y
destrúyanla con `destruir_asg.sh`. La demo completa es la de esta guía.

## Checklist del día

- [ ] Rama correcta y último commit (`git log -1`).
- [ ] Laboratorio iniciado, credenciales copiadas y `aws sts get-caller-identity` funcionando.
- [ ] `.env` cargado; `ADMIN_EMAILS`, `DEMO_EMAIL` y `DEMO_PASSWORD` exportados.
- [ ] `desplegar.sh` terminado, 40 minutos antes.
- [ ] El verificador dice «Todo listo para la defensa.»
- [ ] 4 o 5 consultas de ejemplo para que el panel muestre datos.
- [ ] Pestañas abiertas: `/armar/asistente`, `/observabilidad`, `/docs`, `/api/v1/ml/dashboard`.
- [ ] (SageMaker) `bash EP3_ITY1102/infra/intentar_sagemaker.sh`, para mostrar el error de permisos actual.
- [ ] Al terminar: `destruir.sh`.
- [ ] No mostrar en pantalla la terminal con el `.env` ni las credenciales. Si se vieron, cambien la llave de Gemini.
