# Node connector only. The Pi-Dev-Ops Python image is the repo-root Dockerfile.
FROM node:22-bookworm-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY server.js ./
COPY adapters ./adapters
COPY lib ./lib

ENV NODE_ENV=production

CMD ["npm", "start"]
