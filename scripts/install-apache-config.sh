#!/usr/bin/env bash
# Install the Apache reverse-proxy config for Meal Planner.
#
# Reads the template at scripts/meal-planner.conf.template, substitutes the
# port and mount path, drops it into /etc/apache2/sites-available/, enables
# the required modules and the site, and reloads Apache.
#
# Requires root (Apache config lives under /etc/apache2).
#
# Optional env vars:
#   MEAL_PLANNER_PORT=8000        must match scripts/deploy.sh
#   MENUAPP_ROOT_PATH=/meal-planner
#   APACHE_SITE_NAME=meal-planner   .conf filename (without extension)

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: this script must run as root (Apache config paths need it)." >&2
    exit 1
fi

if ! command -v apache2 >/dev/null 2>&1 && ! command -v a2ensite >/dev/null 2>&1; then
    echo "ERROR: apache2 doesn't look installed (a2ensite not found)." >&2
    echo "Install it first:  apt install apache2" >&2
    exit 1
fi

PORT="${MEAL_PLANNER_PORT:-8000}"
ROOT_PATH="${MENUAPP_ROOT_PATH:-/meal-planner}"
SITE_NAME="${APACHE_SITE_NAME:-meal-planner}"

# Guard against ROOT_PATH values that would break the Location match.
case "$ROOT_PATH" in
    /*)  ;;  # ok, absolute
    *)   echo "ERROR: MENUAPP_ROOT_PATH must start with a slash (got '$ROOT_PATH')." >&2; exit 1 ;;
esac
case "$ROOT_PATH" in
    */)  echo "ERROR: MENUAPP_ROOT_PATH must not end with a slash (got '$ROOT_PATH')." >&2; exit 1 ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$REPO_ROOT/scripts/meal-planner.conf.template"
[ -f "$TEMPLATE" ] || { echo "ERROR: template not found at $TEMPLATE" >&2; exit 1; }

DEST="/etc/apache2/sites-available/${SITE_NAME}.conf"

echo "==> Installing Apache config"
echo "    source:    $TEMPLATE"
echo "    dest:      $DEST"
echo "    port:      $PORT"
echo "    root_path: $ROOT_PATH"
echo "    site:      $SITE_NAME"

# ---- Render the template -----------------------------------------------
sed \
    -e "s|__PORT__|${PORT}|g" \
    -e "s|__ROOT_PATH__|${ROOT_PATH}|g" \
    "$TEMPLATE" > "$DEST"

# ---- Enable required Apache modules ------------------------------------
echo "==> Enabling required Apache modules"
a2enmod proxy proxy_http headers >/dev/null

# ---- Enable the site ---------------------------------------------------
echo "==> Enabling site $SITE_NAME"
a2ensite "$SITE_NAME" >/dev/null

# ---- Validate + reload -------------------------------------------------
echo "==> Validating config (apache2ctl configtest)"
apache2ctl configtest

echo "==> Reloading Apache"
systemctl reload apache2

echo
echo "Done. The app should be reachable at:"
echo "    http://<this-server-ip>${ROOT_PATH}/"
echo
echo "If it isn't, check:"
echo "    tail -f /var/log/apache2/${SITE_NAME}-error.log"
echo "    docker logs meal-planner"
