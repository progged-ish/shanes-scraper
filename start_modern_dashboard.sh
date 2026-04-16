#!/bin/bash
# Script to start the modern dashboard server in the background

echo "Starting modern dashboard server..."
nohup python3 /home/progged-ish/projects/shanes-scraper/dashboard_server_modern.py > /home/progged-ish/projects/shanes-scraper/modern_dashboard.log 2>&1 &
echo "Server started in background. Check http://127.0.0.1:8081/"
echo "Log file: /home/progged-ish/projects/shanes-scraper/modern_dashboard.log"