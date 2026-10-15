# syntax=docker/dockerfile:1
# Build from frontend/:  docker build -t career-intel-frontend frontend
# Debian slim rather than Alpine: package-lock.json is resolved on glibc, and the native
# Tailwind / lightningcss binaries would need their musl variants under Alpine.

ARG NODE_VERSION=24

FROM node:${NODE_VERSION}-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

FROM node:${NODE_VERSION}-slim AS build
WORKDIR /app
# All of these are inlined by `next build`; changing one means rebuilding the image.
# BACKEND_ORIGIN lands in the rewrites (routes-manifest.json), NEXT_PUBLIC_* in the client JS.
ARG BACKEND_ORIGIN=http://api:8000
ARG NEXT_PUBLIC_UMAMI_WEBSITE_ID=
ARG NEXT_PUBLIC_UMAMI_DOMAINS=
ARG NEXT_PUBLIC_UMAMI_DASHBOARD_URL=
ENV BACKEND_ORIGIN=$BACKEND_ORIGIN \
    NEXT_PUBLIC_UMAMI_WEBSITE_ID=$NEXT_PUBLIC_UMAMI_WEBSITE_ID \
    NEXT_PUBLIC_UMAMI_DOMAINS=$NEXT_PUBLIC_UMAMI_DOMAINS \
    NEXT_PUBLIC_UMAMI_DASHBOARD_URL=$NEXT_PUBLIC_UMAMI_DASHBOARD_URL \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:${NODE_VERSION}-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
# Root-owned app files; only the cache directory is writable by the unprivileged node user.
COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
RUN mkdir -p .next/cache && chown node:node .next/cache
USER node
EXPOSE 3000
CMD ["node", "server.js"]
