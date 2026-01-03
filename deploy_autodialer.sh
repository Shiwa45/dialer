#!/bin/bash
# Deployment script for Predictive Autodialer System

echo "========================================="
echo "Predictive Autodialer Deployment Script"
echo "========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if virtual environment exists
if [ ! -d "env" ]; then
    echo -e "${RED}Error: Virtual environment not found${NC}"
    echo "Please create a virtual environment first:"
    echo "  python3 -m venv env"
    exit 1
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source env/bin/activate

# Check if Django is installed
python3 -c "import django" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Django not installed${NC}"
    echo "Please install requirements:"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Create migrations
echo -e "${YELLOW}Creating database migrations...${NC}"
python3 manage.py makemigrations agents
if [ $? -ne 0 ]; then
    echo -e "${RED}Error creating migrations${NC}"
    exit 1
fi

# Apply migrations
echo -e "${YELLOW}Applying database migrations...${NC}"
python3 manage.py migrate
if [ $? -ne 0 ]; then
    echo -e "${RED}Error applying migrations${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Database migrations completed${NC}"
echo ""

# Check if Redis is running
echo -e "${YELLOW}Checking Redis connection...${NC}"
redis-cli ping > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo -e "${RED}Warning: Redis not running${NC}"
    echo "Please start Redis:"
    echo "  sudo systemctl start redis"
else
    echo -e "${GREEN}✓ Redis is running${NC}"
fi

# Check if Asterisk is running
echo -e "${YELLOW}Checking Asterisk connection...${NC}"
asterisk -rx "core show version" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo -e "${RED}Warning: Asterisk not running${NC}"
    echo "Please start Asterisk:"
    echo "  sudo systemctl start asterisk"
else
    echo -e "${GREEN}✓ Asterisk is running${NC}"
fi

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}Deployment completed successfully!${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo "To start the system, run the following commands in separate terminals:"
echo ""
echo -e "${YELLOW}Terminal 1: Django Server${NC}"
echo "  source env/bin/activate && python3 manage.py runserver"
echo ""
echo -e "${YELLOW}Terminal 2: Celery Worker${NC}"
echo "  source env/bin/activate && celery -A autodialer worker -l info"
echo ""
echo -e "${YELLOW}Terminal 3: Predictive Dialer${NC}"
echo "  source env/bin/activate && python3 manage.py predictive_dialer --interval=3"
echo ""
echo -e "${YELLOW}Terminal 4: ARI Event Worker${NC}"
echo "  source env/bin/activate && python3 manage.py ari_event_worker"
echo ""
echo -e "${YELLOW}Terminal 5: WebSocket Server (Daphne)${NC}"
echo "  source env/bin/activate && daphne -b 0.0.0.0 -p 8001 autodialer.asgi:application"
echo ""
echo "Or use the provided start scripts:"
echo "  ./start_all_services.sh"
echo ""
