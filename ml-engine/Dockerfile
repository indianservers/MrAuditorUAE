FROM node:24-bookworm-slim
WORKDIR /app/ml-engine
COPY package*.json ./
RUN npm ci --omit=dev
COPY dist ./dist
USER node
ENTRYPOINT ["node", "--max-old-space-size=1536", "dist/src/worker.js"]
