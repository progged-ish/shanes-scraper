#!/bin/bash
# Script to stop the modern dashboard server

echo "Stopping modern dashboard server..."
pkill -f "dashboard_server_modern.py"
echo "Server stopped."