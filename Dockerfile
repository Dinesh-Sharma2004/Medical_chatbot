FROM node:20-slim AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --force

COPY frontend/ ./
RUN npm run build

FROM python:3.10-slim AS backend

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/cache/huggingface \
    HF_HUB_CACHE=/cache/huggingface

RUN mkdir -p /cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libopenblas-dev

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


RUN apt-get purge -y build-essential libopenblas-dev && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

COPY backend ./backend
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN mkdir -p /app/vectorstore /app/data

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
