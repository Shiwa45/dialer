#!/bin/bash
# Kill all autodialer processes

echo "🛑 Stopping all autodialer processes..."

# Kill by process name
pkill -9 -f "manage.py ari_worker"
pkill -9 -f "manage.py hopper_fill"
pkill -9 -f "manage.py predictive_dialer"
pkill -9 -f "celery.*worker"
pkill -9 -f "celery.*beat"
pkill -9 -f "daphne"

# Also kill any Daphne on port 80
sudo lsof -ti:80 | xargs -r sudo kill -9

echo "✅ All processes killed"
echo ""
echo "You can now run: ./start_autodialer.sh"
