#!/bin/sh
set -eu

# NGINX_SERVER_NAME: optional, override server_name in config

CONF_TARGET="/etc/nginx/conf.d/waskita.conf"

# Optional server_name override
if [ -n "${NGINX_SERVER_NAME:-}" ]; then
  echo "[entrypoint] Overriding server_name to: ${NGINX_SERVER_NAME}"
  
  # Create temporary file for sed operation to avoid 'resource busy' error
  sed "s/server_name localhost;/server_name ${NGINX_SERVER_NAME};/" "${CONF_TARGET}" > "${CONF_TARGET}.tmp"
  
  # Only move if the temp file was created successfully and is different
  if [ -f "${CONF_TARGET}.tmp" ]; then
    if ! cmp -s "${CONF_TARGET}" "${CONF_TARGET}.tmp"; then
      mv -f "${CONF_TARGET}.tmp" "${CONF_TARGET}"
      echo "[entrypoint] Server name updated successfully"
    else
      rm -f "${CONF_TARGET}.tmp"
      echo "[entrypoint] Server name already set correctly"
    fi
  fi
fi

# Remove default server config to avoid shadowing our config
if [ -f "/etc/nginx/conf.d/default.conf" ]; then
  rm -f "/etc/nginx/conf.d/default.conf"
  echo "[entrypoint] Removed default.conf to prevent default_server shadowing"
fi

# Print active config (useful for debugging), do not fail hard if it errors
nginx -T || true

exec nginx -g 'daemon off;'