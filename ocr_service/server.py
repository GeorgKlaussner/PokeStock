from __future__ import annotations

import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class OCRHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_text("ok")
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/ocr":
            self.send_error(404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            self.send_error(400, "Missing image body")
            return

        image_bytes = self.rfile.read(content_length)
        try:
            text = run_tesseract(image_bytes)
        except RuntimeError as error:
            self.send_error(500, str(error))
            return

        self._send_text(text)

    def log_message(self, format: str, *args) -> None:
        return

    def _send_text(self, text: str) -> None:
        encoded = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run_tesseract(image_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".image") as image_file:
        image_file.write(image_bytes)
        image_file.flush()
        try:
            result = subprocess.run(
                ["tesseract", image_file.name, "stdout", "--psm", "6"],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(f"Tesseract failed: {error}") from error
    return result.stdout


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8080), OCRHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()

