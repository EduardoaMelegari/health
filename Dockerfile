FROM python:3.12-slim

ENV TZ=America/Sao_Paulo \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/health.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir flask gunicorn anthropic

COPY . .

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "app:app"]
