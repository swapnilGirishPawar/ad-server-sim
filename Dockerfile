# syntax=docker/dockerfile:1

# ---- Stage 1: build the React dashboard ----
FROM node:20-alpine AS dashboard
WORKDIR /dash
COPY dashboard/package*.json ./
RUN npm install --no-audit --no-fund
COPY dashboard/ ./
RUN npm run build

# ---- Stage 2: Python backend (serves API + built dashboard) ----
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=dashboard /dash/dist /dashboard/dist

ENV DASHBOARD_DIST=/dashboard/dist \
    SIM_DB_PATH=/data/sim.db \
    PYTHONUNBUFFERED=1
RUN mkdir -p /data

EXPOSE 8090
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
