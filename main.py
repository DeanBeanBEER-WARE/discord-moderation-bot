import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

def run_dummy_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
    server = HTTPServer(("", 8080), Handler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

import asyncio
from core.bot import start_bot

if __name__ == "__main__":
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        print("Bot is shutting down...")
    except Exception as e:
        print(f"An error occurred: {e}") 