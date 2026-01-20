#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "============================================"
echo "   🚀 MiroThinker Docker Launcher"
echo "============================================"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}✗ Docker is not running. Please start Docker and try again.${NC}"
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠ .env file not found!${NC}"
    if [ -f .env.docker.example ]; then
        echo -e "${BLUE}Copying .env.docker.example to .env${NC}"
        cp .env.docker.example .env
        echo -e "${YELLOW}⚠ Please edit .env file with your API keys before continuing.${NC}"
        exit 1
    else
        echo -e "${RED}✗ .env.docker.example not found. Please create .env file manually.${NC}"
        exit 1
    fi
fi

# Parse command line arguments
COMMAND=${1:-up}
SERVICE=${2:-}
WITH_NGINX=false

# Check for --with-nginx flag
for arg in "$@"; do
    if [ "$arg" == "--with-nginx" ]; then
        WITH_NGINX=true
    fi
done

# Function to show usage
show_usage() {
    echo "Usage: ./docker-launch.sh [command] [service] [options]"
    echo ""
    echo "Commands:"
    echo "  up              Start all services (default)"
    echo "  down            Stop all services"
    echo "  restart         Restart all services"
    echo "  logs            View logs"
    echo "  build           Build Docker images"
    echo "  ps              Show running containers"
    echo "  clean           Remove containers, volumes, and images"
    echo ""
    echo "Services (optional):"
    echo "  api-server      MiroThinker API Server"
    echo "  gradio-demo     Gradio Demo UI"
    echo "  nginx           Nginx reverse proxy"
    echo ""
    echo "Options:"
    echo "  --with-nginx    Include Nginx reverse proxy"
    echo ""
    echo "Examples:"
    echo "  ./docker-launch.sh up                    # Start all services"
    echo "  ./docker-launch.sh up api-server         # Start only API server"
    echo "  ./docker-launch.sh up --with-nginx       # Start with Nginx"
    echo "  ./docker-launch.sh logs gradio-demo      # View Gradio logs"
    echo "  ./docker-launch.sh restart api-server    # Restart API server"
    echo "  ./docker-launch.sh down                  # Stop all services"
    echo ""
}

# Function to start services
start_services() {
    echo -e "${BLUE}📦 Starting MiroThinker services...${NC}"
    echo ""
    
    COMPOSE_CMD="docker compose"
    
    if [ "$WITH_NGINX" == true ]; then
        COMPOSE_CMD="$COMPOSE_CMD --profile with-nginx"
    fi
    
    if [ -n "$SERVICE" ]; then
        echo -e "${BLUE}Starting service: ${SERVICE}${NC}"
        $COMPOSE_CMD up -d $SERVICE
    else
        $COMPOSE_CMD up -d
    fi
    
    if [ $? -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✓ Services started successfully!${NC}"
        echo ""
        show_status
    else
        echo -e "${RED}✗ Failed to start services${NC}"
        exit 1
    fi
}

# Function to stop services
stop_services() {
    echo -e "${BLUE}🛑 Stopping MiroThinker services...${NC}"
    
    if [ -n "$SERVICE" ]; then
        docker compose stop $SERVICE
    else
        docker compose down
    fi
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Services stopped${NC}"
    else
        echo -e "${RED}✗ Failed to stop services${NC}"
        exit 1
    fi
}

# Function to restart services
restart_services() {
    echo -e "${BLUE}🔄 Restarting MiroThinker services...${NC}"
    
    if [ -n "$SERVICE" ]; then
        docker compose restart $SERVICE
    else
        docker compose restart
    fi
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Services restarted${NC}"
        show_status
    else
        echo -e "${RED}✗ Failed to restart services${NC}"
        exit 1
    fi
}

# Function to show logs
show_logs() {
    if [ -n "$SERVICE" ]; then
        docker compose logs -f $SERVICE
    else
        docker compose logs -f
    fi
}

# Function to build images
build_images() {
    echo -e "${BLUE}🔨 Building Docker images...${NC}"
    
    if [ -n "$SERVICE" ]; then
        docker compose build $SERVICE
    else
        docker compose build
    fi
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Images built successfully${NC}"
    else
        echo -e "${RED}✗ Failed to build images${NC}"
        exit 1
    fi
}

# Function to show status
show_status() {
    echo "============================================"
    echo "   📊 Service Status"
    echo "============================================"
    docker compose ps
    echo ""
    echo "Service URLs:"
    
    # Get ports from .env or use defaults
    API_PORT=$(grep -E "^API_PORT=" .env | cut -d '=' -f2 || echo "8000")
    GRADIO_PORT=$(grep -E "^GRADIO_PORT=" .env | cut -d '=' -f2 || echo "7860")
    NGINX_HTTP_PORT=$(grep -E "^NGINX_HTTP_PORT=" .env | cut -d '=' -f2 || echo "80")
    
    if docker compose ps | grep -q "mirothinker-api.*Up"; then
        echo -e "${GREEN}  ✓ API Server:    http://localhost:${API_PORT}${NC}"
        echo -e "    - Health:       http://localhost:${API_PORT}/health"
        echo -e "    - API Docs:     http://localhost:${API_PORT}/docs"
    fi
    
    if docker compose ps | grep -q "mirothinker-gradio.*Up"; then
        echo -e "${GREEN}  ✓ Gradio Demo:   http://localhost:${GRADIO_PORT}${NC}"
    fi
    
    if docker compose ps | grep -q "mirothinker-nginx.*Up"; then
        echo -e "${GREEN}  ✓ Nginx:         http://localhost:${NGINX_HTTP_PORT}${NC}"
    fi
    
    echo ""
}

# Function to clean up
clean_up() {
    echo -e "${YELLOW}⚠  This will remove all containers, volumes, and images${NC}"
    read -p "Are you sure? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}🧹 Cleaning up...${NC}"
        docker compose down -v --rmi all
        echo -e "${GREEN}✓ Cleanup complete${NC}"
    else
        echo "Cleanup cancelled"
    fi
}

# Main command handler
case "$COMMAND" in
    up|start)
        start_services
        ;;
    down|stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    logs)
        show_logs
        ;;
    build)
        build_images
        ;;
    ps|status)
        show_status
        ;;
    clean)
        clean_up
        ;;
    help|-h|--help)
        show_usage
        ;;
    *)
        echo -e "${RED}Unknown command: $COMMAND${NC}"
        echo ""
        show_usage
        exit 1
        ;;
esac

