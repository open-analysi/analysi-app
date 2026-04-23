# Development stage — Vite dev server with hot reload
FROM node:22-alpine AS dev
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
EXPOSE 5173
CMD ["npx", "vite", "--host"]

# Build stage — compile static assets
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_BACKEND_API_URL=http://localhost:8000
ARG VITE_BACKEND_API_TENANT=default
ARG VITE_DISABLE_AUTH=false
ARG VITE_E2E_API_KEY=
RUN npm run build

# Production stage — unprivileged nginx serving static files + API reverse proxy
#
# Uses nginxinc/nginx-unprivileged so the container runs as UID 101 from boot:
#   * listens on 8080 (non-privileged), not 80
#   * writes temp/pid files under /tmp (no chown needed at startup)
#   * no CAP_* needed — drop ALL capabilities at the pod level
# This eliminates the class of regression where someone drops capabilities
# on the helm deployment and nginx crash-loops on chown/bind.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS production
COPY --from=build /app/dist /usr/share/nginx/html
COPY <<'TMPL' /etc/nginx/templates/default.conf.template
server {
    listen 8080;
    root /usr/share/nginx/html;
    index index.html;

    # Reverse proxy: /api/v1/... → backend /v1/... (strips /api prefix)
    location /api/ {
        proxy_pass ${BACKEND_API_URL}/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # Cache static assets aggressively (Vite adds content hashes)
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # SPA fallback — serve index.html for client-side routes
    location / {
        try_files $uri $uri/ /index.html;
    }
}
TMPL
# nginx image auto-runs envsubst on /etc/nginx/templates/*.template → /etc/nginx/conf.d/
ENV BACKEND_API_URL=http://localhost:8000
EXPOSE 8080
