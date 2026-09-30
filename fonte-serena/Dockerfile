FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    TZ=America/Sao_Paulo

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY wsgi.py .

RUN useradd --system --uid 1000 --home /app app \
    && mkdir -p /data/uploads \
    && chown -R app:app /data

USER app
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=4)" || exit 1

CMD ["gunicorn", "--preload", "-b", "0.0.0.0:8000", "-w", "2", "--threads", "4", "--timeout", "60", "--access-logfile", "-", "wsgi:app"]
