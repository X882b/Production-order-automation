FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so code changes don't trigger a reinstall
COPY server/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY server /app/server

ENV SERVER_HOST=0.0.0.0 SERVER_PORT=8000
EXPOSE 8000
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
