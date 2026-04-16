#!/usr/bin/env python3
"""
Script to create a modern dark mode dashboard without the map component.
"""

import os
import re
from datetime import datetime

def create_modern_dashboard():
    """Create a modern dark mode dashboard from the existing HTML."""
    
    # Input and output paths
    input_path = '/home/progged-ish/projects/shanes-scraper/data/shanes_nws_dashboard_v2.html'
    output_path = '/home/progged-ish/projects/shanes-scraper/data/shanes_nws_dashboard_v2_modern.html'
    
    # Read the original dashboard
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Define the modern dark mode CSS
    modern_css = """
    <style>
        :root {
            --bg-primary: #1a1a2e;
            --bg-secondary: #16213e;
            --bg-card: #0f3460;
            --bg-hover: #1a1a2e;
            --text-primary: #eeeeee;
            --text-secondary: #b2b2b2;
            --accent-primary: #007acc;
            --accent-secondary: #00a8cc;
            --border-color: #2d4059;
            --success: #4caf50;
            --warning: #ff9800;
            --danger: #f44336;
            --info: #2196f3;
        }
        
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 0;
            margin: 0;
        }
        
        .dashboard-container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        header {
            background: linear-gradient(135deg, var(--bg-secondary), var(--bg-card));
            padding: 2rem;
            border-radius: 10px;
            margin-bottom: 2rem;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            text-align: center;
        }
        
        h1 {
            color: var(--accent-secondary);
            margin-bottom: 1rem;
            font-size: 2.5rem;
        }
        
        .version-info {
            background: rgba(0, 122, 204, 0.15);
            padding: 1rem;
            border-radius: 8px;
            border-left: 4px solid var(--accent-primary);
            margin: 1rem 0;
        }
        
        .state-navigation {
            background: var(--bg-card);
            padding: 1.5rem;
            border-radius: 10px;
            margin-bottom: 2rem;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        }
        
        .state-navigation h2 {
            color: var(--accent-secondary);
            margin-bottom: 1rem;
            text-align: center;
        }
        
        .state-links {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 0.5rem;
        }
        
        .state-links a {
            background: var(--accent-primary);
            color: white;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            text-decoration: none;
            transition: all 0.3s ease;
            font-weight: 500;
        }
        
        .state-links a:hover {
            background: var(--accent-secondary);
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0, 168, 204, 0.3);
        }
        
        .keyword-section {
            background: var(--bg-card);
            padding: 2rem;
            border-radius: 10px;
            margin-bottom: 2rem;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        }
        
        .keyword-section h2 {
            color: var(--accent-secondary);
            margin-bottom: 1.5rem;
            text-align: center;
        }
        
        details {
            background: var(--bg-secondary);
            border-radius: 8px;
            margin-bottom: 1rem;
            padding: 1rem;
            border-left: 4px solid var(--accent-primary);
        }
        
        summary {
            cursor: pointer;
            font-weight: bold;
            padding: 0.5rem;
            color: var(--accent-secondary);
            list-style: none;
        }
        
        summary::-webkit-details-marker {
            display: none;
        }
        
        summary::before {
            content: "▶ ";
            margin-right: 0.5rem;
        }
        
        details[open] summary::before {
            content: "▼ ";
        }
        
        .office-section {
            background: var(--bg-card);
            padding: 2rem;
            border-radius: 10px;
            margin-bottom: 2rem;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        }
        
        .office-section h2 {
            color: var(--accent-secondary);
            border-bottom: 2px solid var(--border-color);
            padding-bottom: 0.5rem;
            margin-bottom: 1.5rem;
        }
        
        .office-card {
            background: var(--bg-secondary);
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            border-left: 4px solid var(--accent-primary);
        }
        
        .office-card h3 {
            color: var(--accent-secondary);
            margin-bottom: 1rem;
        }
        
        .ai-summary {
            background: rgba(0, 122, 204, 0.15);
            padding: 1rem;
            border-radius: 6px;
            margin: 1rem 0;
            border-left: 4px solid var(--accent-primary);
        }
        
        .ai-summary::before {
            content: "🤖 AI Summary:";
            font-weight: bold;
            color: var(--accent-secondary);
            display: block;
            margin-bottom: 0.5rem;
        }
        
        .keyword-features {
            margin: 1rem 0;
        }
        
        .keyword-features h4 {
            color: var(--accent-secondary);
            margin: 1rem 0;
        }
        
        ul {
            padding-left: 1.5rem;
        }
        
        li {
            margin: 0.5rem 0;
        }
        
        pre {
            background: var(--bg-secondary);
            color: var(--text-primary);
            padding: 1rem;
            border-radius: 6px;
            overflow-x: auto;
            font-size: 0.9rem;
            line-height: 1.4;
        }
        
        a {
            color: var(--accent-secondary);
            text-decoration: none;
        }
        
        a:hover {
            text-decoration: underline;
        }
        
        .back-to-top {
            display: inline-block;
            margin-top: 1rem;
            padding: 0.5rem 1rem;
            background: var(--accent-primary);
            color: white;
            text-decoration: none;
            border-radius: 4px;
            transition: background 0.3s;
        }
        
        .back-to-top:hover {
            background: var(--accent-secondary);
        }
        
        footer {
            text-align: center;
            padding: 2rem;
            color: var(--text-secondary);
            font-size: 0.9rem;
        }
        
        @media (max-width: 768px) {
            .dashboard-container {
                padding: 10px;
            }
            
            header {
                padding: 1rem;
            }
            
            h1 {
                font-size: 1.8rem;
            }
            
            .state-links {
                gap: 0.3rem;
            }
            
            .state-links a {
                padding: 0.3rem 0.8rem;
                font-size: 0.9rem;
            }
        }
    </style>
    """
    
    # Remove the map section
    # Find and remove the map pane
    map_pattern = r'<div class="map-pane">.*?</div>'
    content = re.sub(map_pattern, '', content, flags=re.DOTALL)
    
    # Remove folium script
    folium_pattern = r"<script src='https://cdn\.jsdelivr\.net/npm/folium@.*?</script>"
    content = re.sub(folium_pattern, '', content)
    
    # Remove leaflet scripts and CSS
    leaflet_patterns = [
        r'&lt;script src=&quot;https://cdn\.jsdelivr\.net/npm/leaflet@.*?&lt;/script&gt;',
        r'&lt;link rel=&quot;stylesheet&quot; href=&quot;https://cdn\.jsdelivr\.net/npm/leaflet@.*?/&gt;',
        r'&lt;link rel=&quot;stylesheet&quot; href=&quot;https://cdnjs\.cloudflare\.com/ajax/libs/Leaflet\.awesome-markers/.*?/&gt;'
    ]
    
    for pattern in leaflet_patterns:
        content = re.sub(pattern, '', content)
    
    # Remove existing styles (we'll replace with our modern CSS)
    style_pattern = r'<style>.*?</style>'
    content = re.sub(style_pattern, modern_css, content, flags=re.DOTALL)
    
    # Add viewport meta tag for mobile responsiveness if not present
    if '<meta name="viewport"' not in content:
        head_end = content.find('</head>')
        if head_end != -1:
            viewport_meta = '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            content = content[:head_end] + viewport_meta + content[head_end:]
    
    # Write the modern dashboard
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Modern dark mode dashboard created at: {output_path}")
    
    # Also create the server script for the modern dashboard
    create_server_script()

def create_server_script():
    """Create a server script for the modern dashboard."""
    server_script = '''#!/usr/bin/env python3
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
        print("\\n🛑 Server stopped by user.")
        server.shutdown()

if __name__ == '__main__':
    main()
'''
    
    script_path = '/home/progged-ish/projects/shanes-scraper/dashboard_server_modern.py'
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(server_script)
    
    # Make the script executable
    os.chmod(script_path, 0o755)
    
    print(f"Modern dashboard server script created at: {script_path}")

if __name__ == '__main__':
    create_modern_dashboard()