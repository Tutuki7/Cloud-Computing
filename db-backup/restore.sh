#!/bin/bash
set -e

DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-cng8}"
DB_NAME="${DB_NAME:-movielens25m}"
DB_PASSWORD="${DB_PASSWORD}"

export PGPASSWORD="$DB_PASSWORD"

echo "waiting for postgres to be ready..."
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
    echo "  postgres not ready yet, retrying in 3s..."
    sleep 3
done
echo "postgres is ready."

echo "restoring database from backup.dump..."
pg_restore \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    /db/backup.dump

echo ""
echo " database restore complete."
