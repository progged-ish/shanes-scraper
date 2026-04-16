#!/bin/bash
# Wrapper script to run shanes_nws_scraper_v8.py with a 600-second timeout
cd /home/progged-ish/projects/shanes-scraper
timeout 600 python3 shanes_nws_scraper_v8.py
