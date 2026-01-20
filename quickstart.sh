#!/bin/bash

# Quick start script for MiroThinker
# This script provides shortcuts to common operations

echo "🚀 MiroThinker Quick Start"
echo ""
echo "What would you like to do?"
echo ""
echo "1) Start all services with Docker (recommended)"
echo "2) Start API Server only"
echo "3) Start Gradio Demo only"
echo "4) View service status"
echo "5) View logs"
echo "6) Stop all services"
echo "7) Exit"
echo ""
read -p "Enter your choice [1-7]: " choice

case $choice in
    1)
        echo ""
        echo "Starting all services with Docker..."
        ./docker-launch.sh up
        ;;
    2)
        echo ""
        echo "Starting API Server..."
        cd apps/api-server
        ./start.sh
        ;;
    3)
        echo ""
        echo "Starting Gradio Demo..."
        cd apps/gradio-demo
        echo "⚠️  Please run manually:"
        echo "cd apps/gradio-demo"
        echo "uv run python main.py"
        ;;
    4)
        echo ""
        ./docker-launch.sh ps
        ;;
    5)
        echo ""
        ./docker-launch.sh logs
        ;;
    6)
        echo ""
        ./docker-launch.sh down
        ;;
    7)
        echo "Goodbye!"
        exit 0
        ;;
    *)
        echo "Invalid choice. Please run again."
        exit 1
        ;;
esac

