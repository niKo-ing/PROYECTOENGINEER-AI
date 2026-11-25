# Imagen de PRODUCCIÓN del frontend: compila una vez y sirve con `next start`.
# (Con `next dev`, Next 16 bloquea sus propios archivos cuando se entra por una IP que no es localhost: en AWS la
# página quedaba en «Cargando…».)
FROM node:24-slim AS deps
WORKDIR /app
RUN npm install -g pnpm@11.3.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM deps AS build
# Next fija los rewrites de /api/v1 al compilar: la URL del backend va como argumento de construcción.
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL NEXT_TELEMETRY_DISABLED=1
COPY . .
RUN pnpm build

FROM node:24-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build --chown=node:node /app ./
USER node
EXPOSE 3000
CMD ["node_modules/.bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
