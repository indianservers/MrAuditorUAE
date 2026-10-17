FROM node:24-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0 NEXT_TELEMETRY_DISABLED=1
RUN addgroup -g 10001 -S auditos && adduser -u 10001 -S auditos -G auditos
COPY --from=build --chown=auditos:auditos /app/.next/standalone ./
COPY --from=build --chown=auditos:auditos /app/.next/static ./.next/static
COPY --from=build --chown=auditos:auditos /app/public ./public
USER auditos
EXPOSE 3000
CMD ["node","server.js"]
