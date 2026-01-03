FROM node:20-alpine AS base

WORKDIR /app

# Build stage
FROM base AS builder
COPY package*.json ./
RUN npm ci

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
