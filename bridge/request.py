import json
import threading
import http.server
import asyncio
from astrbot.api import logger


class RequestHandler(http.server.SimpleHTTPRequestHandler):
    """_summary_

    Args:
        http (_type_): _description_
    """
    future: asyncio.Future = None  # type: ignore

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == "/update":
            try:
                content_length = int(self.headers["Content-Length"])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data)

                session_id = data.get("sessionId")
                message_id = data.get("messageId")

                if session_id and message_id:
                    logger.info(
                        f"成功从浏览器捕获到ID\n - Session ID: {session_id}\n  - Message ID: {message_id}"
                    )
                    if RequestHandler.future and not RequestHandler.future.done():
                        RequestHandler.future.set_result((session_id, message_id))

                    self.send_response(200)
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(b'{"status": "success"}')
                    threading.Thread(target=self.server.shutdown).start()

                else:
                    self.send_response(400, "Bad Request")
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(b'{"error": "Missing sessionId or messageId"}')
            except Exception as e:
                self.send_response(500, "Internal Server Error")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(
                    f'{{"error": "Internal server error: {e}"}}'.encode("utf-8")
                )
        else:
            self.send_response(404, "Not Found")
            self._send_cors_headers()
            self.end_headers()
