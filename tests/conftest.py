"""Shared pytest fixtures for integration wiring tests."""

import json
import threading
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer  # pylint: disable=no-name-in-module
from unittest.mock import MagicMock

import pytest

from modules.cdp.proxy import ProxyPool


@pytest.fixture
def mock_webdriver():
    """WebDriver-like mock with key browser methods pre-mocked."""
    driver = MagicMock()
    driver.execute_script = MagicMock(return_value=None)
    driver.delete_all_cookies = MagicMock(return_value=None)
    driver.execute_cdp_cmd = MagicMock(return_value=None)
    driver.find_element = MagicMock()
    driver.find_elements = MagicMock(return_value=[])
    driver.current_url = "https://example.test"
    return driver


class _BitBrowserMockHandler(BaseHTTPRequestHandler):
    """Tiny BitBrowser API mock server for tests."""

    _lock = threading.Lock()
    _calls = []  # pylint: disable=dangerous-default-value

    @classmethod
    def reset_calls(cls):
        with cls._lock:
            cls._calls = []

    @classmethod
    def snapshot_calls(cls):
        with cls._lock:
            return list(cls._calls)

    def _write_json(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # pylint: disable=invalid-name
        self._write_json({"data": []})

    def do_POST(self):  # pylint: disable=invalid-name
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        with self._lock:
            self._calls.append((self.path, payload))
        if self.path == "/api/v1/browser/create":
            self._write_json({"data": {"id": "profile-1"}})
            return
        if self.path == "/api/v1/browser/open":
            self._write_json({"data": {"webdriver": "ws://127.0.0.1:9222/profile-1"}})
            return
        self._write_json({"ok": True})

    def log_message(self, _format, *_args):  # noqa: A002
        return


@pytest.fixture
def mock_bitbrowser_server():
    """Start a local mock BitBrowser HTTP server and yield context data."""
    _BitBrowserMockHandler.reset_calls()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _BitBrowserMockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield {
            "endpoint": f"http://{host}:{port}",
            "snapshot_calls": _BitBrowserMockHandler.snapshot_calls,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def proxy_pool_3():
    """Three-proxy pool fixture for worker assignment tests."""
    return ProxyPool(["socks5://p1:1080", "socks5://p2:1080", "socks5://p3:1080"])
