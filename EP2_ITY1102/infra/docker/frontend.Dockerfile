# Imagen de producción del frontend (Next.js). El Dockerfile de frontend/ usa `pnpm dev` (desarrollo).
# Se construye desde la raíz del repositorio:
#   docker build -f EP2_ITY1102/infra/docker/frontend.Dockerfile \
#     --build-arg NEXT_PUBLIC_SUPABASE_URL=... --build-arg NEXT_PUBLIC_SUPABASE_ANON_KEY=... \
#     -t todobarato-frontend frontend

FROM node:24-slim AS build
WORKDIR /app
RUN npm install -g pnpm@11.3.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
# Las NEXT_PUBLIC_* quedan incrustadas en el bundle al compilar.
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
# El backend vive en el mismo host, en la red de Docker, con el alias «backend».
ARG BACKEND_URL=http://backend:8000
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    BACKEND_URL=$BACKEND_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN pnpm build && pnpm prune --prod

FROM node:24-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 BACKEND_URL=http://backend:8000
RUN npm install -g pnpm@11.3.0
COPY --from=build --chown=node:node /app ./
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["pnpm", "start", "--hostname", "0.0.0.0", "--port", "3000"]
