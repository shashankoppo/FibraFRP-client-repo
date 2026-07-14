FROM node:18-alpine

ENV NODE_ENV=production

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev

COPY server.js ./

USER node

EXPOSE 3000
CMD ["node", "server.js"]
