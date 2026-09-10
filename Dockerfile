# ── Stage 1: Build React frontend ────────────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
# VITE_API_URL empty = relative URLs → FastAPI serves both API and frontend
RUN npm run build

# ── Stage 2: Production backend ───────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Python dependencies (psycopg2 removed — SQLite is built into Python)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Application source
COPY backend/ ./backend/

# Built frontend — main.py resolves this as __file__/../../frontend/dist
COPY --from=frontend-build /frontend/dist ./frontend/dist

# Python needs to find 'app.*' modules inside backend/
ENV PYTHONPATH=/app/backend

# SQLite database lives in /data — mount a Code Engine volume here for persistence.
# If no volume is mounted, /data is ephemeral (in-container only, wiped on restart).
# Data re-seeds from sources after each restart in that case.
ENV DATABASE_URL=sqlite:////data/alm_market_voice.db

# Non-root user for security
RUN useradd -m -u 1001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

# Production: no --reload, 2 workers
# Note: SQLite + multiple workers is safe because WAL mode allows concurrent reads,
# and we use a pool_size=1 per worker to avoid write contention.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
