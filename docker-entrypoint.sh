#!/bin/sh
set -eu

echo "🚀 Starting Waskita Docker Entrypoint"

if [ ! -f "/app/.env.docker" ]; then
  echo "⚠️  .env.docker file not found, using default environment variables"
  echo "📝 Creating complete .env file for Docker environment"
  env | sort > /app/.env
  echo "✅ Complete .env file created successfully for Docker using environment variables"
else
  cp /app/.env.docker /app/.env
fi

echo "⏳ Waiting for PostgreSQL database to be ready..."
DB_HOST="${DATABASE_HOST:-db}"
DB_PORT="${DATABASE_PORT:-5432}"
DB_USER="${DATABASE_USER:-admin}"

for i in $(seq 1 30); do
  if pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" >/dev/null 2>&1; then
    echo "✅ Database connection successful"
    echo "✅ Database is ready!"
    break
  fi
  sleep 2
done

echo "🔧 Always running database initialization to apply environment variables..."
echo "📊 Initializing database..."
python /app/init_database.py || true

exec "$@"