# Build the static bundle, then serve it from nginx. The dev server is not used
# in compose -- see the `web` service comments for the hot-reload alternative.
FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Baked in at build time: Vite inlines import.meta.env at compile, so this cannot
# be changed by setting an environment variable on the running container.
ARG VITE_API_BASE=http://localhost:8001
ENV VITE_API_BASE=$VITE_API_BASE

RUN npm run build

FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
