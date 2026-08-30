FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN if [ -s package-lock.json ]; then npm ci --omit=dev; else npm install --omit=dev; fi

COPY server.js ./

ENV NODE_ENV=production
EXPOSE 3000

CMD ["npm", "start"]
