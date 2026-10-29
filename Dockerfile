# BEC Guard: the website (React, built here) and the API (FastAPI) in one container.
# Hugging Face Spaces (Docker SDK) sends traffic to port 7860 and runs the container as user 1000.

FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app app/ app/
COPY --chown=app data/ data/
COPY --chown=app scenarios/ scenarios/
COPY --chown=app fixtures/ fixtures/
COPY --chown=app --from=ui /ui/dist frontend/dist
USER app
ENV PYTHONUNBUFFERED=1
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers", "--forwarded-allow-ips", "*"]
