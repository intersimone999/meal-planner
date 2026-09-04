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

# Runtime env vars (all optional):
#   MENUAPP_PASSWORD                 → master password. If unset the login
#                                      page accepts anything and every route
#                                      is open (dev mode); a warning is logged.
#   MENUAPP_SESSION_SECRET           → session-cookie signing key. If unset,
#                                      a random one is generated per process
#                                      start (sessions won't survive restart).
#   MENUAPP_HTTPS_ONLY=true          → set when serving over HTTPS so the
#                                      session cookie is marked Secure.
#   MENUAPP_ROOT_PATH=/meal-planner  → set when the app runs behind a
#                                      reverse-proxy sub-path. Templates and
#                                      redirect headers auto-prefix with it.

EXPOSE 8000

# CMD is a shell form so `${MENUAPP_ROOT_PATH:+…}` can conditionally add
# --root-path (needed only when the app is proxied at a sub-path). Also
# --forwarded-allow-ips="*" so uvicorn honours X-Forwarded-* from any local
# proxy (the container is only reachable from the host anyway).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' ${MENUAPP_ROOT_PATH:+--root-path \"$MENUAPP_ROOT_PATH\"}"]
