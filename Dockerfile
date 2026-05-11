# Stage 1: Build React frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/webapp
COPY webapp/package*.json ./
RUN npm install
COPY webapp/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY .env.example ./
COPY somly.jpg.jpg ./

# Copy built frontend from stage 1
COPY --from=frontend-builder /app/webapp/dist ./webapp/dist

# Expose the port Railway assigns
EXPOSE ${PORT:-8000}

# Start the bot
CMD ["python", "-m", "src.bot"]
