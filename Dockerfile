FROM node:22-bookworm-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY python/requirements.txt ./python/
RUN pip3 install --no-cache-dir --break-system-packages -r python/requirements.txt

COPY package.json package-lock.json* ./
RUN npm ci --omit=dev || npm install --omit=dev

COPY tsconfig.json ./
COPY src ./src
COPY python ./python

RUN npm install typescript && npm run build && npm prune --omit=dev

ENV NODE_ENV=production
ENV PYTHON_PATH=python3
ENV PORT=8080

EXPOSE 8080

CMD ["node", "dist/server.js"]
