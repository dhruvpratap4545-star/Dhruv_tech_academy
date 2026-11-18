# Web app image, deployed to Cloud Run as `dhruv-web`. Build context is frontend/:
#   docker build -t dhruv-web frontend
# nginx serves the built app and proxies /api/* to the API service named by BACKEND_HOST
# (runtime env, e.g. dhruv-api-xxxxxxxxxx.asia-southeast1.run.app — host only, no https://).

# --- Stage 1: build ---------------------------------------------------------------------
FROM node:24-slim AS build
WORKDIR /web

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# Relative: the browser calls the API on the same origin, whatever the host name is.
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build && node scripts/build-csp.mjs dist/index.html > csp.conf

# --- Stage 2: serve ---------------------------------------------------------------------
FROM nginxinc/nginx-unprivileged:1.27-alpine

ENV PORT=8080 \
    NGINX_ENVSUBST_FILTER="^(PORT|BACKEND_HOST)$"

COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /web/csp.conf /etc/nginx/snippets/csp.conf
COPY --from=build /web/dist /usr/share/nginx/html

EXPOSE 8080
