# ─── base ────────────────────────────────────────────────────────────────────
FROM node:20-alpine AS base
WORKDIR /app
ENV NODE_ENV=development
# Disable Next.js telemetry — prevents anonymous data being sent to Vercel
# during builds and dev, and avoids unnecessary network requests in containers.
ENV NEXT_TELEMETRY_DISABLED=1

# ─── deps ────────────────────────────────────────────────────────────────────
# Installed once, reused by dev + builder stages.
FROM base AS deps
COPY package*.json ./
RUN npm ci

# ─── dev ─────────────────────────────────────────────────────────────────────
# Source code is mounted via docker-compose volume.
# node_modules come from the deps stage (named volume prevents host overwrite).
FROM base AS dev
COPY --from=deps /app/node_modules ./node_modules
EXPOSE 3000
CMD ["npm", "run", "dev"]

# ─── builder ─────────────────────────────────────────────────────────────────
# Produces .next/standalone — requires output: 'standalone' in next.config.ts
FROM base AS builder
ENV NODE_ENV=production
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ─── prod ────────────────────────────────────────────────────────────────────
# Minimal image — only the standalone output, no node_modules bloat.
FROM node:20-alpine AS prod
ENV NODE_ENV=production
WORKDIR /app

RUN addgroup --system --gid 1001 nodejs && \
    adduser  --system --uid 1001 nextjs

# standalone build already includes the minimal server + its own node_modules
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static    ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public          ./public

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
CMD ["node", "server.js"]
