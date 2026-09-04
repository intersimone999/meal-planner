#!/usr/bin/env bash
# Install the Apache reverse-proxy config for Meal Planner.
#
# Reads the template at scripts/meal-planner.conf.template, substitutes
# port + mount path, drops it into /etc/apache2/conf-available/, enables
# the required modules and the conf, reloads Apache.
#
# Config lives under conf-available/ (not sites-available/) on purpose:
# it's not a full VirtualHost, just extra proxy rules that attach to
# whichever *:80 vhost is already the default (usually 000-default.conf).
# That way we don't fight over which vhost catches the request.
#
# Requires root.
#
# Optional env vars:
#   MEAL_PLANNER_PORT=8000        must match the port in docker-compose.yml
#   MENUAPP_ROOT_PATH=/meal-planner
#   APACHE_CONF_NAME=meal-planner  .conf filename (without extension)

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: this script must run as root (Apache config paths need it)." >&2
    exit 1
fi

if ! command -v a2enconf >/dev/null 2>&1; then
    echo "ERROR: apache2 doesn't look installed (a2enconf not found)." >&2
    echo "Install it first:  apt install apache2" >&2
    exit 1
fi

PORT="${MEAL_PLANNER_PORT:-8000}"
ROOT_PATH="${MENUAPP_ROOT_PATH:-/meal-planner}"
CONF_NAME="${APACHE_CONF_NAME:-meal-planner}"

# Guard against ROOT_PATH values that would break the ProxyPass rules.
case "$ROOT_PATH" in
    /*)  ;;
    *)   echo "ERROR: MENUAPP_ROOT_PATH must start with a slash (got '$ROOT_PATH')." >&2; exit 1 ;;
esac
case "$ROOT_PATH" in
    */)  echo "ERROR: MENUAPP_ROOT_PATH must not end with a slash (got '$ROOT_PATH')." >&2; exit 1 ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$REPO_ROOT/scripts/meal-planner.conf.template"
[ -f "$TEMPLATE" ] || { echo "ERROR: template not found at $TEMPLATE" >&2; exit 1; }

DEST="/etc/apache2/conf-available/${CONF_NAME}.conf"

echo "==> Installing Apache config"
echo "    source:    $TEMPLATE"
echo "    dest:      $DEST"
echo "    port:      $PORT"
echo "    root_path: $ROOT_PATH"
echo "    conf:      $CONF_NAME"

# ---- Render the template -----------------------------------------------
sed \
    -e "s|__PORT__|${PORT}|g" \
    -e "s|__ROOT_PATH__|${ROOT_PATH}|g" \
    "$TEMPLATE" > "$DEST"

# ---- Enable required Apache modules ------------------------------------
echo "==> Enabling required Apache modules"
a2enmod proxy proxy_http headers >/dev/null

# ---- Enable the conf ---------------------------------------------------
echo "==> Enabling conf $CONF_NAME"
a2enconf "$CONF_NAME" >/dev/null

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
echo "    tail -f /var/log/apache2/error.log"
echo "    docker logs meal-planner"
