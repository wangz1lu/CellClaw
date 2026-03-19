#!/usr/bin/env python3
"""Simple dashboard server"""
import http.server
import socketserver
import json
import urllib.request
import os

# Clear proxy for localhost connections
for var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
    os.environ.pop(var, None)
os.environ['no_proxy'] = 'localhost,127.0.0.1'

PORT = 7860
API_PORT = 19766

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/'):
            endpoint = self.path[4:]
            self.proxy(f"http://127.0.0.1:{API_PORT}{endpoint}")
        elif self.path == '/' or self.path == '/index.html':
            self.path = '/dashboard.html'
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/api/chat':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            self.proxy(f"http://127.0.0.1:{API_PORT}/chat", body)
        else:
            self.send_response(404)
            self.end_headers()
    
    def proxy(self, url, data=None):
        try:
            req = urllib.request.Request(url, data=data)
            req.add_header('Content-Type', 'application/json')
            with urllib.request.urlopen(req, timeout=10) as resp:
                self.send_response(resp.status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(resp.read())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

print(f"🧬 Dashboard: http://127.0.0.1:{PORT}")
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
