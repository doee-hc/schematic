"""Local viewer for one schematic JSON file."""

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from schematic.graph import tree_of
from schematic.render import draw

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")
MAX_BODY_BYTES = 2 * 1024 * 1024


def _safe_static_path(url_path):
    if url_path in ("/", "/index.html"):
        return os.path.join(STATIC_DIR, "index.html")
    if not url_path.startswith("/static/"):
        return None
    rel = unquote(url_path[len("/static/"):])
    rel = rel.replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        return None
    path = os.path.abspath(os.path.join(STATIC_DIR, rel))
    if not path.startswith(STATIC_DIR + os.sep):
        return None
    return path


def make_handler(document, filename):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            if self.server.log_to_stderr:
                BaseHTTPRequestHandler.log_message(self, fmt, *args)

        def _read_body(self):
            length = self.headers.get("Content-Length")
            if length is None:
                raise ValueError("missing Content-Length")
            size = int(length)
            if size < 0 or size > MAX_BODY_BYTES:
                raise ValueError("request too large")
            return self.rfile.read(size)

        def _send_bytes(self, status, content_type, data):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, payload, status=200):
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send_bytes(status, "application/json; charset=utf-8", data)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/document":
                swatches = document.get("swatches") or []
                self._send_json({
                    "ok": True,
                    "name": filename,
                    "palette": document.get("palette") or {},
                    "swatches": swatches,
                    "tree": tree_of(document["root"]),
                })
                return
            static_path = _safe_static_path(path)
            if static_path is None or not os.path.isfile(static_path):
                self._send_json({"ok": False, "error": "Not Found"}, 404)
                return
            ext = os.path.splitext(static_path)[1].lower()
            ctypes = {
                ".html": "text/html; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".svg": "image/svg+xml",
            }
            ctype = ctypes.get(ext) or (mimetypes.guess_type(static_path)[0] or "application/octet-stream")
            with open(static_path, "rb") as handle:
                data = handle.read()
            self._send_bytes(200, ctype, data)

        def do_POST(self):
            path = urlparse(self.path).path
            if path != "/api/draw":
                self._send_json({"ok": False, "error": "Not Found"}, 404)
                return
            try:
                raw = self._read_body()
                body = json.loads(raw.decode("utf-8") or "{}")
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, 400)
                return
            if not isinstance(body, dict):
                self._send_json({"ok": False, "error": "JSON 无效"}, 400)
                return
            include = body.get("include") or []
            if not include:
                self._send_json({"ok": False, "error": "请至少勾选一个节点"}, 400)
                return
            options = {
                "include": include,
                "port_include": body.get("port_include") or [],
                "port_exclude": body.get("port_exclude") or [],
                "boxes_only": bool(body.get("boxes_only")),
                "palette": body.get("palette") or {},
            }
            try:
                svg = draw(document, options)
            except Exception as exc:
                self._send_json({"ok": False, "error": "出图失败: %s" % exc}, 500)
                return
            stem = os.path.splitext(filename)[0] or "graph"
            self._send_json({"ok": True, "filename": stem + ".svg", "svg": svg})

    return Handler


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, handler, log_to_stderr=False):
        self.log_to_stderr = log_to_stderr
        ThreadingHTTPServer.__init__(self, server_address, handler)


def serve(document, filename, host="127.0.0.1", port=8765, verbose=False):
    server = QuietThreadingHTTPServer(
        (host, port), make_handler(document, filename), log_to_stderr=verbose,
    )
    print("Schematic: http://%s:%s" % (host, port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
