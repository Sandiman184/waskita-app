#!/bin/sh
set -eu

# ENABLE_SSL: true/false to choose which Nginx config to use
# NGINX_SERVER_NAME: optional, override server_name in chosen config

SSL="${ENABLE_SSL:-true}"
CONF_TARGET="/etc/nginx/conf.d/waskita.conf"

if [ "$SSL" = "true" ] || [ "$SSL" = "1" ] || [ "$SSL" = "yes" ]; then
  cp /etc/nginx/waskita.ssl.conf "$CONF_TARGET"
  echo "[entrypoint] Using SSL config: /etc/nginx/waskita.ssl.conf"
else
  cp /etc/nginx/waskita.http.conf "$CONF_TARGET"
  echo "[entrypoint] Using HTTP-only config: /etc/nginx/waskita.http.conf"
fi

# Optional server_name override
if [ -n "${NGINX_SERVER_NAME:-}" ]; then
  # Replace the first occurrence of server_name line in the server block
  sed -i "s/^\s*server_name\s\+.*;/    server_name ${NGINX_SERVER_NAME};/" "$CONF_TARGET"
  echo "[entrypoint] server_name set to: ${NGINX_SERVER_NAME}"
fi

# Remove default server config to avoid shadowing our config
if [ -f "/etc/nginx/conf.d/default.conf" ]; then
  rm -f "/etc/nginx/conf.d/default.conf"
  echo "[entrypoint] Removed default.conf to prevent default_server shadowing"
fi

# Print active config (useful for debugging), do not fail hard if it errors
nginx -T || true

exec nginx -g 'daemon off;'