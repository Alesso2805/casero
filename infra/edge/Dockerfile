FROM node:26-trixie-slim AS web
RUN npm install --global pnpm@12.15.0
WORKDIR /build/web
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY docs/legal /build/docs/legal
COPY web/ ./
RUN pnpm run build

FROM caddy:2.11
COPY infra/caddy/Caddyfile.prod /etc/caddy/Caddyfile
COPY --from=web /build/web/dist /srv
