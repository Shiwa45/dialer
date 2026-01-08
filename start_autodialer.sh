#!/bin/bash
# Quick Start Script for Autodialing System
# Usage: ./start_autodialer.sh

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "========================================="
echo "  Autodialer System - Quick Start"
echo "========================================="
echo ""

# Check if virtual environment exists
if [ ! -d "env" ]; then
    echo "❌ Virtual environment not found!"
    echo "Please create it first: python3 -m venv env"
    exit 1
fi

# Activate virtual environment
source env/bin/activate

# Force Postgres connection params for all child processes (avoids socket/host ambiguity)
export PGHOST=127.0.0.1
export PGPORT=5432
export PGUSER=postgres
export PGPASSWORD=Shiwansh@123
# Check if migrations are applied
echo "📋 Checking database migrations..."
python manage.py showmigrations campaigns | grep -q "\[X\] 0015_hopper_system" || {
    echo "⚠️  Hopper system migration not applied!"
    echo "Running migrations..."
    python manage.py migrate
}

echo "✅ Database ready"
echo ""


# Check for Redis
echo "📋 Checking Redis..."
if ! python -c "import redis; print(redis.Redis().ping())" &> /dev/null; then
    echo "❌ Redis is not potentially reachable or installed."
    echo "Please ensure Redis is running: sudo systemctl start redis"
    # Attempt to start if linux
    if command -v systemctl &> /dev/null; then
         echo "Attempting to start Redis..."
         sudo systemctl start redis || echo "⚠️ Could not start Redis automatically."
    fi
fi
echo "✅ Redis appears to be running (or at least python check passed/skipped)"

# Deploy Asterisk Configs
echo "📋 Deploying Asterisk Configuration..."
# Standard paths
PJSIP_CONF="/etc/asterisk/pjsip_custom.conf"
EXT_CONF="/etc/asterisk/extensions_custom.conf"

if [ -f "./generated_configs/pjsip_custom.conf" ]; then
    echo "Copying config files (sudo required)..."
    sudo cp ./generated_configs/pjsip_custom.conf "$PJSIP_CONF"
    sudo cp ./generated_configs/extensions_custom.conf "$EXT_CONF"
    sudo asterisk -rx "core reload"
    echo "✅ Asterisk Config Refreshed"
else
    echo "⚠️  Generated configs not found. Skipping deployment."
fi

echo ""


# Create logs directory
mkdir -p logs

# Array to store PIDs
PIDS=()

# Function to start a service in background
start_service() {
    local name=$1
    local command=$2
    local log_file="logs/${name// /_}.log"
    
    echo "Starting $name... (Log: $log_file)"
    $command > "$log_file" 2>&1 &
    local pid=$!
    PIDS+=($pid)
    echo "  ↳ PID: $pid"
}

# Cleanup function
cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    for pid in "${PIDS[@]}"; do
        if kill -0 $pid 2>/dev/null; then
            echo "  Killing PID $pid..."
            kill $pid
        fi
    done
    echo "✅ All services stopped."
    exit
}

# Trap Ctrl+C (SIGINT) and exit
trap cleanup SIGINT EXIT

echo "🚀 Starting services..."
echo ""

# Start ARI Worker
echo "1️⃣  Starting ARI Worker..."
start_service "ARI Worker" "./env/bin/python -u manage.py ari_worker"
sleep 2

# Start Hopper Fill
echo "2️⃣  Starting Hopper Fill..."
start_service "Hopper Fill" "./env/bin/python -u manage.py hopper_fill"
sleep 1

# Start Predictive Dialer
echo "3️⃣  Starting Predictive Dialer..."
start_service "Predictive Dialer" "./env/bin/python -u manage.py predictive_dialer"
sleep 1

# Start Django Server (ASGI/Channels)
echo "4️⃣  Starting Django Server (Daphne)..."
start_service "Django Server" "./env/bin/daphne -b 0.0.0.0 -p 8000 autodialer.asgi:application"
sleep 2

echo ""
echo "========================================="
echo "  ✅ All Services Started!"
echo "========================================="
echo ""
echo "📊 Access Points:"
echo "  • Agent Dashboard:    http://localhost:8000/agents/dashboard/"
echo "  • Admin Panel:        http://localhost:8000/admin/"
echo ""
echo "Logs are being written to the 'logs/' directory."
echo "Press Ctrl+C to stop all services."
echo ""

# Keep script running by waiting for PIDs
wait
