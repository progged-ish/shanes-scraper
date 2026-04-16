#!/usr/bin/env python3
"""
Simple HTTP server to serve the modern NWS dashboard HTML file on localhost.
"""

import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

# Configuration
HOST = '127.0.0.1'
PORT = 8081  # Using a different port to avoid conflict
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
DASHBOARD_FILE = os.path.join(DATA_DIR, 'shanes_nws_dashboard_v2_modern.html')

class DashboardHandler(SimpleHTTPRequestHandler):
    """Custom handler to serve the modern dashboard file."""
    
    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        
        # Serve the dashboard file for root path
        if parsed_path.path == '/' or parsed_path.path == '/dashboard.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            try:
                content = open(DASHBOARD_FILE, 'r', encoding='utf-8').read()
                self.send_header('Content-Length', len(content.encode()))
            except:
                self.send_header('Content-Length', 0)
            self.end_headers()
            try:
                with open(DASHBOARD_FILE, 'r', encoding='utf-8') as f:
                    self.wfile.write(f.read().encode('utf-8'))
            except:
                self.wfile.write(b'')
        
        # Serve static files from current directory
        else:
            super().do_GET()
    
    def do_HEAD(self):
        """Handle HEAD requests."""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/' or parsed_path.path == '/dashboard.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
        else:
            super().do_HEAD()
    
    def log_message(self, format, *args):
        """Custom log format."""
        print(f"[{self.log_date_time_string()}] {args[0]}")

def main():
    """Start the HTTP server."""
    # Check if dashboard file exists
    if not os.path.exists(DASHBOARD_FILE):
        print(f"✗ Modern dashboard file not found: {DASHBOARD_FILE}")
        print(f"   Run the create_modern_dashboard.py script first.")
        sys.exit(1)
    
    print("=" * 60)
    print("🌐 Starting Modern Dashboard Server...")
    print("=" * 60)
    print(f"   Server URL: http://{HOST}:{PORT}/")
    print(f"   Dashboard file: {DASHBOARD_FILE}")
    print(f"   Press Ctrl+C to stop the server.")
    print("=" * 60)
    
    try:
        server = HTTPServer((HOST, PORT), DashboardHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user.")
        server.shutdown()

if __name__ == '__main__':
    main()
