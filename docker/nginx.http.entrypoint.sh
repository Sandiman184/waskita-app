#!/bin/sh
# Entrypoint khusus untuk HTTP-only mode

# Print active config untuk debugging
echo "=== NGINX HTTP-ONLY CONFIGURATION ==="
nginx -T || true

echo "=== STARTING NGINX (HTTP-ONLY) ==="
exec nginx -g 'daemon off;'