# Ripple API — OR-Tools CP-SAT requires an always-on container host.
# This image will NOT work on Vercel/Lambda serverless (native binary size
# and cold-start limits). Deploy to Render / Fly.io / Railway.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so layer caching survives source edits.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

COPY seed ./seed
COPY tests ./tests

# Run as non-root.
RUN useradd --create-home --uid 10001 ripple && chown -R ripple:ripple /app
USER ripple

ENV PORT=8000
EXPOSE 8000

# Fail the container early if CP-SAT cannot actually solve on this host.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,json,os,sys; \
b=json.load(urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/health')); \
sys.exit(0 if b.get('solver_ready') else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
