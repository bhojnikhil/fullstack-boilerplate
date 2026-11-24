FROM node:20-alpine AS base

WORKDIR /app

# Build stage
FROM base AS builder
COPY package*.json ./
RUN npm ci

# NEXT_PUBLIC_* values are inlined into the bundle by `next build`, so the
# public API URL must be provided at build time (env files are excluded from
# the build context). It must be reachable from the user's browser.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

COPY . .
RUN npm run build

# Production stage
FROM base
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY package*.json ./

EXPOSE 3000

CMD ["npm", "start"]
