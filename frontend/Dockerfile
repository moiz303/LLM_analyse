FROM node:20-alpine AS deps
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@12.3.4 --activate
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM node:20-alpine AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@12.3.4 --activate
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_GRAFANA_DASHBOARD_URL=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_GRAFANA_DASHBOARD_URL=$NEXT_PUBLIC_GRAFANA_DASHBOARD_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
NEXT_TELEMETRY_DISABLED=1 \
PORT=3000 \
HOSTNAME=0.0.0.0
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL
RUN corepack enable && corepack prepare pnpm@12.3.4 --activate
COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/next.config.mjs /app/postcss.config.mjs /app/tsconfig.json ./

EXPOSE 3000
CMD ["pnpm", "start"]
