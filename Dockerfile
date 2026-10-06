FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY server /app/server

RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] python-dotenv SQLAlchemy psycopg2-binary \
    requests pydantic meilisearch watchdog python-docx

ENV SERVER_HOST=0.0.0.0 SERVER_PORT=8000
EXPOSE 8000
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
