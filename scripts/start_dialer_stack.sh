#!/usr/bin/env bash
# Helper to start dialer background services: Celery worker, Celery beat, and ARI worker.
# Usage: ./scripts/start_dialer_stack.sh

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Starting Celery worker..."
env/bin/celery -A autodialer worker -l info &
WORKER_PID=$!

echo "Starting Celery beat..."
env/bin/celery -A autodialer beat -l info &
BEAT_PID=$!

echo "Starting ARI worker..."
env/bin/python manage.py ari_worker &
ARI_PID=$!

echo "Services started:"
echo "  Celery worker PID: $WORKER_PID"
echo "  Celery beat   PID: $BEAT_PID"
echo "  ARI worker    PID: $ARI_PID"
echo
echo "Press Ctrl+C to stop all."

trap "echo 'Stopping...'; kill $WORKER_PID $BEAT_PID $ARI_PID 2>/dev/null" INT TERM
wait
