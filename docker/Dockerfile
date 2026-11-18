# PQ-SSE cloud server (python -m pqsse.server) for Linux.
#
#   docker build -f docker/Dockerfile -t pqsse-server .
#   docker compose -f docker/docker-compose.yml up -d
#
# The image holds the server code only (no desktop app, no keys, no data). The store, the blobs, the TLS
# certificate and the admin token live in the /data volume. The passphrase that protects the server's keys
# comes from the Docker secret pqsse_passphrase, never from an environment variable or the command line.
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PQSSE_SERVER_DATA_DIR=/data \
    PQSSE_SERVER_HOST=0.0.0.0 \
    PQSSE_SERVER_PORT=8443 \
    PQSSE_SERVER_ADMIN_HOST=127.0.0.1 \
    PQSSE_SERVER_ADMIN_PORT=8444

RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin pqsse \
 && mkdir -p /app /data && chown pqsse:pqsse /data

WORKDIR /app
COPY requirements-server.txt /app/
# exact versions; hashes are added with the reproducible-build work (REALLIFE_PLAN.md milestone 7)
RUN pip install --no-cache-dir -r requirements-server.txt
COPY pyproject.toml /app/
COPY pqsse /app/pqsse

USER pqsse
VOLUME ["/data"]
EXPOSE 8443

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import ssl,urllib.request,json; c=ssl._create_unverified_context(); json.load(urllib.request.urlopen('https://127.0.0.1:8443/v1/time', context=c, timeout=4))" || exit 1

ENTRYPOINT ["python", "-m", "pqsse.server"]
CMD ["run"]
