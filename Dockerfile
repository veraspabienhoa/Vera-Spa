FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# libpq5 cho PostgreSQL; postgresql-client cung cap pg_dump/pg_restore cho migration; ca-certificates cho HTTPS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 postgresql-client ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.cache/pip

COPY . .

# Cloud Run service dung CMD nay. Cloud Run Job se override command/args thanh:
#   python timesoft_sync_job.py
CMD ["sh", "-c", "streamlit run app.py --server.address=0.0.0.0 --server.port=${PORT:-8080} --server.headless=true --browser.gatherUsageStats=false"]
