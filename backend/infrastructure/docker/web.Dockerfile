FROM node:22-alpine AS build
WORKDIR /app
COPY apps/web/package*.json ./
RUN npm install
COPY apps/web ./
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY infrastructure/docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
