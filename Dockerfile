FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYVISTA_OFF_SCREEN=true \
    TRAME_DEFAULT_HOST=0.0.0.0 \
    TRAME_SERVER=true \
    CBCL_MODEL_LIBRARY=/app/models \
    CBCL_CACHE_DIR=/app/cache

RUN apt-get update && apt-get install -y --no-install-recommends \
    libegl1 \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libxt6 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --no-cache-dir --upgrade pip \
  && python -m pip install --no-cache-dir .

RUN mkdir -p /app/models /app/cache

EXPOSE 8080

CMD ["python", "-m", "cbcl_model_viewer", "--models", "/app/models", "--cache", "/app/cache", "--host", "0.0.0.0", "--port", "8080"]
