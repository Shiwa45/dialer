#!/usr/bin/env bash
# Helper to start dialer background services: Celery, ARI worker, Hopper Fill, and Predictive Dialer
# Usage: ./scripts/start_dialer_stack.sh

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "========================================="
echo "  Starting Autodialer Stack"
echo "========================================="
echo ""

# Check if virtual environment exists
if [ ! -d "env" ]; then
    echo "❌ Virtual environment not found!"
    echo "Please create it first: python3 -m venv env"
    exit 1
fi

echo "Starting Celery worker..."
env/bin/celery -A autodialer worker -l info &
WORKER_PID=$!
sleep 1

echo "Starting Celery beat..."
env/bin/celery -A autodialer beat -l info &
BEAT_PID=$!
sleep 1

echo "Starting ARI worker..."
env/bin/python manage.py ari_worker &
ARI_PID=$!
sleep 2

echo "Starting Hopper Fill service..."
env/bin/python manage.py hopper_fill &
HOPPER_PID=$!
sleep 1

echo "Starting Predictive Dialer..."
env/bin/python manage.py predictive_dialer &
DIALER_PID=$!
sleep 1

echo ""
echo "========================================="
echo "  ✅ All Services Started!"
echo "========================================="
echo ""
echo "Services running:"
echo "  • Celery worker    PID: $WORKER_PID"
echo "  • Celery beat      PID: $BEAT_PID"
echo "  • ARI worker       PID: $ARI_PID"
echo "  • Hopper Fill      PID: $HOPPER_PID"
echo "  • Predictive Dialer PID: $DIALER_PID"
echo ""
echo "📊 Access Points:"
echo "  • Agent Dashboard:   http://localhost:8000/agents/dashboard/"
echo "  • Admin Panel:       http://localhost:8000/admin/"
echo "  • Monitor Dashboard: http://localhost:8000/reports/monitor/"
echo ""
echo "📝 To start Django server (in another terminal):"
echo "  env/bin/python manage.py runserver"
echo ""
echo "Press Ctrl+C to stop all services."
echo ""

trap "echo ''; echo 'Stopping all services...'; kill $WORKER_PID $BEAT_PID $ARI_PID $HOPPER_PID $DIALER_PID 2>/dev/null; echo 'All services stopped.'" INT TERM
wait
