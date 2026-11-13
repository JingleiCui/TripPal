FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
WORKDIR /integrations
COPY integrations/package*.json ./
RUN npm ci --omit=dev

FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libstdc++6 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.lock.txt requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY backend/ ./backend/
COPY migrations/ ./migrations/
COPY docs/upstream/ ./docs/upstream/
COPY alembic.ini config.example.json ./
COPY scripts/server.py ./scripts/server.py
COPY --from=web /usr/local/bin/node /usr/local/bin/node
COPY --from=web /web/dist ./frontend/dist
COPY --from=web /integrations ./integrations
RUN pip install --no-deps . && useradd --create-home traveler && mkdir -p /app/data && chown -R traveler:traveler /app
USER traveler
ENV PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=2
EXPOSE 8808
CMD ["python","scripts/server.py"]
