#!/bin/bash
set -e

# Wait for database
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
  echo "Waiting for database ($DB_HOST:$DB_PORT)..."
  sleep 2
done

# Execute command
echo "Starting Odoo..."
exec "$@" -c "$ODOO_RC" \
  --db_host="$DB_HOST" \
  --db_port="$DB_PORT" \
  --db_user="$DB_USER" \
  --db_password="$DB_PASSWORD"
