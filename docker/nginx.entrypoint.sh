#!/bin/sh
# set -e  # Disabled for Alpine Linux compatibility

# Environment variables for SSL certificate paths
SSL_CERT_PATH="${SSL_CERT_PATH:-/etc/letsencrypt/live/waskita.site/fullchain.pem}"
SSL_KEY_PATH="${SSL_KEY_PATH:-/etc/letsencrypt/live/waskita.site/privkey.pem}"

# NGINX_SERVER_NAME: optional, override server_name in config

CONF_TARGET="/etc/nginx/conf.d/waskita.conf"

if [ -n "${NGINX_SERVER_NAME:-}" ]; then
  echo "[entrypoint] Server name override requested but config is immutable; skipping"
fi

# Remove default server config to avoid shadowing our config
if [ -f "/etc/nginx/conf.d/default.conf" ]; then
  rm -f "/etc/nginx/conf.d/default.conf"
  echo "[entrypoint] Removed default.conf to prevent default_server shadowing"
fi

# Print active config (useful for debugging), do not fail hard if it errors
nginx -T || true

exec nginx -g 'daemon off;'