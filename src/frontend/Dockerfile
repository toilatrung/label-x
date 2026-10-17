# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS dependencies
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund

FROM dependencies AS build
ARG NEXT_PUBLIC_API_BASE_URL=""
ARG LABELX_API_PROXY_TIMEOUT_MS=300000
ENV NODE_ENV=production NEXT_PUBLIC_AUTH_MODE=backend \
    NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    LABELX_API_PROXY_TIMEOUT_MS=${LABELX_API_PROXY_TIMEOUT_MS} \
    NODE_OPTIONS=--max-old-space-size=3072
COPY . .
RUN npm run build

FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0 \
    LABELX_API_PROXY_TARGET=http://labelx-backend:8000
LABEL org.opencontainers.image.source="https://github.com/toilatrung/label-x" \
      org.opencontainers.image.title="LabelX frontend"
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
