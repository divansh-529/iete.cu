# Production image for Render (or any container host). See docs/09-deployment.md.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

RUN useradd --create-home appuser
USER appuser

# Check the database connection (clear message in the deploy log if it fails), apply pending
# migrations, then serve. Render provides $PORT.
CMD ["sh", "-c", "python -m app.cli db-check && alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
