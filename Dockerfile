FROM node:20-slim AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --force

COPY frontend/ ./

RUN npm run build


FROM python:3.10-slim AS backend

ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/cache/huggingface \
    HF_HUB_CACHE=/cache/huggingface

RUN mkdir -p /cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    git \
    curl \
    wget \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    libjpeg62-turbo \
    zlib1g \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend

COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN mkdir -p /app/vectorstore /app/data

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--log-level", "info", \
     "--proxy-headers"]
