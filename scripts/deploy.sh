#!/usr/bin/env bash
# Meal Planner — one-shot deployment on the target host.
# Builds (if missing) the Docker image and (re)starts the container.
#
# Required env vars — the script REFUSES to run if any are unset or empty:
#   MENUAPP_PASSWORD          master password for the login page
#   MENUAPP_SESSION_SECRET    signing key for the session cookie
#                             (any long random string — do NOT change once set
#                             or all sessions get invalidated)
#
# Optional env vars (shown with their defaults):
#   MEAL_PLANNER_PORT=8000                  host-side port (bound to 127.0.0.1)
#   MEAL_PLANNER_DATA_DIR=/var/lib/meal-planner   host dir for the SQLite file
#   MEAL_PLANNER_IMAGE=meal-planner:latest        docker image tag
#   MEAL_PLANNER_CONTAINER=meal-planner           container name
#   MENUAPP_ROOT_PATH=/meal-planner         URL sub-path where Apache mounts
#                                           the app (leave unset for root)
#   MENUAPP_HTTPS_ONLY=true                 mark the session cookie Secure
#
# Example:
#   MENUAPP_PASSWORD=… MENUAPP_SESSION_SECRET=$(openssl rand -hex 32) \
#     scripts/deploy.sh

set -euo pipefail

# ---- Fundamentals: fail loudly if unset or empty --------------------------
: "${MENUAPP_PASSWORD:?MENUAPP_PASSWORD must be set (master password).}"
: "${MENUAPP_SESSION_SECRET:?MENUAPP_SESSION_SECRET must be set (session signing key).}"

# ---- Optional with defaults ---------------------------------------------
PORT="${MEAL_PLANNER_PORT:-8000}"
DATA_DIR="${MEAL_PLANNER_DATA_DIR:-/var/lib/meal-planner}"
IMAGE="${MEAL_PLANNER_IMAGE:-meal-planner:latest}"
CONTAINER="${MEAL_PLANNER_CONTAINER:-meal-planner}"
ROOT_PATH="${MENUAPP_ROOT_PATH:-/meal-planner}"
HTTPS_ONLY="${MENUAPP_HTTPS_ONLY:-false}"

# Resolve script's containing repo (so `scripts/deploy.sh` and
# `./deploy.sh` from the scripts dir both work).
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: docker not found in PATH." >&2
    exit 1
fi

echo "==> Meal Planner deploy"
echo "    image:       $IMAGE"
echo "    container:   $CONTAINER"
echo "    port:        127.0.0.1:$PORT"
echo "    data dir:    $DATA_DIR"
echo "    root_path:   ${ROOT_PATH:-<root>}"
echo "    https_only:  $HTTPS_ONLY"

# ---- Ensure data dir exists ---------------------------------------------
mkdir -p "$DATA_DIR"

# ---- Build image if missing ---------------------------------------------
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "==> Building $IMAGE from $REPO_ROOT"
    docker build -t "$IMAGE" "$REPO_ROOT"
else
    echo "==> Image $IMAGE already present (skip build; delete + rerun to rebuild)."
fi

# ---- Stop / remove existing container ------------------------------------
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "==> Removing existing container $CONTAINER"
    docker rm -f "$CONTAINER" >/dev/null
fi

# ---- Run -----------------------------------------------------------------
echo "==> Starting $CONTAINER"
docker run -d \
    --name "$CONTAINER" \
    --restart unless-stopped \
    -p "127.0.0.1:${PORT}:8000" \
    -v "$DATA_DIR:/data" \
    -e MENUAPP_PASSWORD="$MENUAPP_PASSWORD" \
    -e MENUAPP_SESSION_SECRET="$MENUAPP_SESSION_SECRET" \
    -e MENUAPP_HTTPS_ONLY="$HTTPS_ONLY" \
    ${ROOT_PATH:+-e MENUAPP_ROOT_PATH="$ROOT_PATH"} \
    "$IMAGE" >/dev/null

# ---- Wait for /healthz ---------------------------------------------------
echo -n "==> Waiting for health check "
for i in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
        echo " OK"
        echo "==> Running: http://127.0.0.1:${PORT}${ROOT_PATH}/"
        exit 0
    fi
    echo -n "."
    sleep 1
done

echo " FAILED"
echo "Container logs:" >&2
docker logs --tail 40 "$CONTAINER" >&2
exit 1
