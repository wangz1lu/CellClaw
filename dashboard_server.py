#!/usr/bin/env python3
"""Simple dashboard server - serves HTML + proxies API"""
import http.server
import socketserver
import json
import urllib.request
import urllib.error

PORT = 7860
API_PORT = 19766

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/stats':
            self proxy('/stats')
        elif self.path == '/api/servers':
            self.proxy('/servers')
        elif self.path == '/api/jobs':
            self.proxy('/jobs')
        elif self.path == '/api/sessions/':
            self.proxy('/sessions/dashboard/history')
        elif self.path == '/':
            self.path = '/dashboard.html'
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == '/api/chat':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            self.proxy('/chat', body)
        else:
            self.send_response(404)
            self.end_headers()
    
    def proxy(self, endpoint, data=None):
        url = f'http://127.0.0.1:{API_PORT}{endpoint}'
        try:
            if data:
                req = urllib.request.Request(url, data=data, method='POST')
                req.add_header('Content-Type', 'application/json')
            else:
                req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                self.send_response(resp.status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
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
print(f"📡 API Proxy: http://127.0.0.1:{PORT}/api/* -> localhost:{API_PORT}")

with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
    httpd.serve_forever()
