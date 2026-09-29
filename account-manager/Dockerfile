FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY wsgi.py gunicorn.conf.py ./

# Unprivileged runtime user; /data holds the SQLite database (mounted as a volume).
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /srv/app --shell /usr/sbin/nologin app \
 && mkdir -p /data && chown -R app:app /data /srv/app

USER 10001:10001
EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status==200 else 1)"

CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:app"]
