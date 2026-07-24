FROM python:3.12-slim

ENV TZ=America/Sao_Paulo \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/health.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# gthread + timeout folgado: o loop do coach (várias chamadas à API) passa fácil
# dos 30 s padrão — o worker seria morto no meio da conversa
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", \
     "--worker-class", "gthread", "--threads", "4", "--timeout", "300", "app:app"]
