FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

RUN chmod +x scripts/start-frontend.sh

EXPOSE 5173

CMD ["sh", "./scripts/start-frontend.sh"]
