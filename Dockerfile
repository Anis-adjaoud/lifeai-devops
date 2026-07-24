# LifeAI — API FastAPI + agents Google ADK (déploiement Cloud Run)
# Le frontend est buildé et servi par CE MÊME service Cloud Run (api.py monte
# frontend_web/dist en StaticFiles) : Firebase Hosting ne transmet pas le header
# Cookie sur ses rewrites vers Cloud Run, ce qui casse les sessions — un seul
# service/origine évite complètement le problème.

FROM node:20-slim AS frontend-build
WORKDIR /app/frontend_web
COPY frontend_web/package.json frontend_web/package-lock.json ./
RUN npm ci
COPY frontend_web/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pré-télécharge le modèle d'embeddings CIQUAL dans l'image : sans ça, chaque
# cold start Cloud Run (scale-to-zero) retéléchargerait ~470 Mo depuis
# HuggingFace avant de pouvoir répondre à la moindre requête.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

COPY api.py .
COPY agentic/ agentic/
COPY nutrition/ nutrition/
COPY data/foods_table.xlsx data/foods_table.xlsx
COPY output/models/ output/models/
COPY --from=frontend-build /app/frontend_web/dist frontend_web/dist

# google_client_secrets.json n'est PAS copié ici : il est gitignored et monté
# au runtime depuis Secret Manager (voir deploy/02_secrets.sh).

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD exec uvicorn api:app --host 0.0.0.0 --port ${PORT:-8080}
