#!/bin/bash
# Restart Celery Workers and Beat Scheduler

echo "Stopping existing Celery processes..."
pkill -f 'celery worker'
pkill -f 'celery beat'

# Wait for processes to stop
sleep 2

echo "Starting Celery worker..."
cd /home/shiwansh/dialer
source env/bin/activate
celery -A autodialer worker -l info &

echo "Starting Celery beat scheduler..."
celery -A autodialer beat -l info &

echo "Celery services restarted successfully!"
echo "Worker PID: $(pgrep -f 'celery worker')"
echo "Beat PID: $(pgrep -f 'celery beat')"
