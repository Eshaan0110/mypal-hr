# My Pal frontend image. Built by docker-compose.yml (profile "app"); see docs/operations.md.
# Stage 1 builds the static files; stage 2 serves them with nginx, which also forwards /api to
# the backend, so the browser talks to one origin (as the Vite dev server does in development).

FROM node:22.21-alpine AS build
WORKDIR /app
# npm ci installs exactly what package-lock.json lists, and fails if it does not match.
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.28-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
