# ============================================================
# GoliTransit Frontend — Dockerfile
# ============================================================
# Two-target Dockerfile:
#   - Default target: Dev server (Vite HMR on port 5173)
#   - Optional "production" target: Nginx serving built assets
#
# Usage (dev):
#   docker build -t golitransit-frontend ./frontend
#   docker run -p 5173:5173 golitransit-frontend
#
# Usage (production):
#   docker build --target production -t golitransit-frontend-prod ./frontend
#   docker run -p 80:80 golitransit-frontend-prod
# ============================================================

# ─── Stage 1: Dependencies ──────────────────────────────────
FROM node:20-alpine AS deps

WORKDIR /app

# Copy package files for dependency caching
COPY package.json package-lock.json* ./

# Install dependencies (clean install for reproducibility)
RUN npm ci --prefer-offline 2>/dev/null || npm install

# ─── Stage 2: Development (default target) ──────────────────
FROM node:20-alpine AS development

WORKDIR /app

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy application source
COPY . .

# Expose Vite dev server port
EXPOSE 5173

# Default: run Vite dev server bound to all interfaces
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]


# ─── Stage 3: Build (for production) ────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

# Copy dependencies
COPY --from=deps /app/node_modules ./node_modules

# Copy source
COPY . .

# Set API URL at build time (can be overridden with --build-arg)
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

# Build production bundle
RUN npm run build


# ─── Stage 4: Production (Nginx) ────────────────────────────
FROM nginx:1.25-alpine AS production

LABEL maintainer="GoliTransit Team"
LABEL description="GoliTransit Frontend — React + Leaflet + TailwindCSS"

# Copy custom Nginx config for SPA routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Expose HTTP port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
