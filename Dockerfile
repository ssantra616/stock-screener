# Dockerfile for US Stock Screener
FROM python:3.11-slim

# Don't write .pyc, unbuffered stdout/stderr (better logs in containers)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first to maximize Docker layer caching
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy app code
COPY . .

# Most platforms inject PORT at runtime; default to 8000 for local docker runs.
ENV PORT=8000
EXPOSE 8000

# Use shell form so $PORT expands. Single worker by default — bump with WORKERS env.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers ${WORKERS:-1}
