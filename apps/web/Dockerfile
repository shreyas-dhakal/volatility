FROM node:22-slim
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
RUN npm ci
COPY astryx-themes.js ./astryx-themes.js
COPY apps/web apps/web
COPY examples/ /app/examples/
ARG API_URL=http://api:8000
ENV API_URL=$API_URL
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build --workspace @galvanise/web
EXPOSE 3000
CMD ["npm", "run", "start", "--workspace", "@galvanise/web", "--", "--hostname", "0.0.0.0"]
