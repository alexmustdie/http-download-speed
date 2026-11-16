import subprocess
import sys
import unittest
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from time import sleep

SCRIPT = Path(__file__).resolve().parents[1] / "download_speed.py"
PAYLOAD = b"x" * 150_000


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path
        self.server.calls[path] += 1
        if path == "/missing":
            self.send_error(404)
            return
        if path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/file")
            self.end_headers()
            return
        if path == "/stall":
            sleep(0.5)
            return

        self.send_response(200)
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.end_headers()
        if path == "/truncated":
            self.wfile.write(PAYLOAD[:100])
            return

        if self.server.body_in_progress:
            self.server.overlap = True
        self.server.body_in_progress = True
        self.wfile.write(PAYLOAD[:100])
        sleep(0.025)
        self.server.body_in_progress = False
        self.wfile.write(PAYLOAD[100:])

    def log_message(self, format, *args):
        pass


class DownloadSpeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.calls = Counter()
        cls.server.body_in_progress = False
        cls.server.overlap = False
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def run_cli(self, path, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), f"http://127.0.0.1:{self.server.server_port}{path}", *args],
            capture_output=True,
            text=True,
            timeout=8,
        )

    def test_ten_sequential_full_downloads_and_report(self):
        result = self.run_cli("/file")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.server.calls["/file"], 10)
        self.assertFalse(self.server.overlap)
        stats = dict(line.split(": ", 1) for line in result.stdout.splitlines())
        self.assertEqual(stats["Requests"], "10")
        total = len(PAYLOAD) * 10
        self.assertEqual(stats["Total downloaded"], f"{total} bytes")
        average = float(stats["Average request time"].split()[0])
        self.assertGreaterEqual(average, 0.024)
        speed = float(stats["Download speed"].split()[0])
        self.assertAlmostEqual(speed, total * 8 / (average * 10 * 1_000_000), delta=0.01)

    def test_http_error_and_redirect_have_no_partial_report(self):
        file_calls = self.server.calls["/file"]
        for path, status in [("/missing", 404), ("/redirect", 302)]:
            with self.subTest(path=path):
                result = self.run_cli(path)
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"Request 1/10 failed: HTTP {status}", result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(self.server.calls[path], 1)
        self.assertEqual(self.server.calls["/file"], file_calls)

    def test_truncated_body_fails(self):
        result = self.run_cli("/truncated")
        self.assertEqual(result.returncode, 1)
        self.assertIn("incomplete response", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_socket_timeout_fails(self):
        result = self.run_cli("/stall", "--timeout", "0.05")
        self.assertEqual(result.returncode, 1)
        self.assertIn("timed out", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_rejects_non_http_url(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "file:///tmp/unused"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("expected an http:// or https:// URL", result.stderr)


if __name__ == "__main__":
    unittest.main()
