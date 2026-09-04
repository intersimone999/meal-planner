FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# SQLite database lives on a mounted volume so data survives container restarts.
ENV MENUAPP_DB_PATH=/data/menuapp.db
VOLUME ["/data"]

# Auth env vars (all optional):
#   MENUAPP_PASSWORD                 → master password. If unset the login
#                                      page accepts anything and every route
#                                      is open (dev mode); a warning is logged.
#   MENUAPP_SESSION_SECRET           → session-cookie signing key. If unset,
#                                      a random one is generated per process
#                                      start (sessions won't survive restart).
#   MENUAPP_HTTPS_ONLY=true          → set when serving over HTTPS so the
#                                      session cookie is marked Secure.

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
