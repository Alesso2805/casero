FROM node:26-trixie-slim
RUN npm install --global pnpm@12.15.0
USER node
WORKDIR /home/node/app
COPY --chown=node:node package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY --chown=node:node . .
CMD ["pnpm", "dev", "--host", "0.0.0.0", "--port", "5173"]
