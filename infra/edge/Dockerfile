FROM node:26-trixie-slim AS web
RUN npm install --global pnpm@12.15.0
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm run build

FROM caddy:2.11
COPY infra/caddy/Caddyfile.prod /etc/caddy/Caddyfile
COPY --from=web /web/dist /srv
