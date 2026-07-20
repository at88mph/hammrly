# Build stage
FROM node:22-alpine AS build
WORKDIR /app
COPY services/portal/package.json services/portal/package-lock.json* ./
RUN npm install
COPY services/portal/ .
ARG VITE_BASE_PATH=/hammrly/portal/
ENV VITE_BASE_PATH=$VITE_BASE_PATH
RUN npm run build

# Runtime
FROM nginx:1.27-alpine
COPY services/portal/nginx.conf.template /etc/nginx/templates/default.conf.template
ENV PORTAL_HTTP_PATH_PREFIX=/hammrly/portal
COPY --from=build /app/dist /usr/share/nginx/html
# config.json is mounted from ConfigMap at /usr/share/nginx/html/config.json
EXPOSE 8080
