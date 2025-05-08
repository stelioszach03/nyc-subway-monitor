FROM node:22.4.0-alpine as build

WORKDIR /app

# Install dependencies
COPY package.json .
COPY tsconfig.json .
RUN npm install -g pnpm@9 && pnpm install

# Build the app
COPY . .
ARG VITE_API_URL
ARG VITE_MAPBOX_TOKEN
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_MAPBOX_TOKEN=$VITE_MAPBOX_TOKEN
RUN pnpm build

# Production image
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
