FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN groupadd --system placeai && useradd --system --gid placeai --home /app placeai

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY --chown=placeai:placeai . .
RUN mkdir -p /app/uploads/resumes && chown -R placeai:placeai /app/uploads

USER placeai
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.app:app --host 0.0.0.0 --port 8000 --workers 2"]
