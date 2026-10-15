"""Local viewer for one schematic JSON file."""

import copy
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from schematic.graph import tree_of
from schematic.document import normalize_document
from schematic.elaborate import elaborate_view, needs_elaboration, resolve_view_module
from schematic.drawio import svg_to_drawio
from schematic.render import draw

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(ROOT, "static")
MAX_BODY_BYTES = 8 * 1024 * 1024


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


def _merged_from_document(doc):
    return {
        "modules": copy.deepcopy(doc.get("modules") or {}),
        "palette": copy.deepcopy(doc.get("palette") or {}),
        "swatches": copy.deepcopy(doc.get("swatches") or []),
        "root": copy.deepcopy(doc.get("root")),
    }


def _set_flat(server, document, filename):
    server.schematic_view_mode = "flat"
    server.schematic_merged = None
    server.schematic_view_module = ""
    server.schematic_document = document
    server.schematic_filename = filename or ""


def _set_hierarchical(server, merged, view_module, filename):
    server.schematic_view_mode = "hierarchical"
    server.schematic_merged = merged
    server.schematic_view_module = view_module
    server.schematic_document = elaborate_view(merged, view_module, set())
    server.schematic_filename = filename or ""


def store_schematic_source(server, raw_doc, filename="", top_cli=None):
    if not isinstance(raw_doc, dict):
        raise ValueError("JSON 无效")
    if raw_doc.get("modules") and needs_elaboration(raw_doc):
        merged = _merged_from_document(raw_doc)
        view_module = resolve_view_module(merged, top_cli)
        _set_hierarchical(server, merged, view_module, filename)
        return
    _set_flat(server, normalize_document(raw_doc), filename)


def document_api_payload(server):
    document = getattr(server, "schematic_document", None)
    filename = getattr(server, "schematic_filename", "") or ""
    if document is None:
        return {
            "ok": True,
            "loaded": False,
            "name": "",
            "palette": {},
            "swatches": [],
            "tree": None,
            "hierarchical": False,
        }
    swatches = document.get("swatches") or []
    payload = {
        "ok": True,
        "loaded": True,
        "name": filename,
        "palette": document.get("palette") or {},
        "swatches": swatches,
        "tree": tree_of(document["root"]),
        "hierarchical": getattr(server, "schematic_view_mode", "flat") == "hierarchical",
    }
    if payload["hierarchical"]:
        merged = getattr(server, "schematic_merged", None) or {}
        payload["view_module"] = getattr(server, "schematic_view_module", "") or ""
        payload["modules"] = sorted((merged.get("modules") or {}).keys())
        payload["expanded_paths"] = []
    return payload


def _parse_open_body(body):
    if not isinstance(body, dict):
        raise ValueError("JSON 无效")
    if isinstance(body.get("document"), dict):
        name = body.get("name")
        if name is not None and not isinstance(name, str):
            raise ValueError("name 须为字符串")
        doc = body["document"]
        label = (name or "").strip() or "design.json"
        return doc, os.path.basename(label) or "design.json"
    if body.get("modules") or isinstance(body.get("root"), dict):
        return body, "design.json"
    raise ValueError("需要 document 或含 root / modules 的电路图 JSON")


def _draw_options(body, hierarchical):
    options = {
        "port_include": body.get("port_include") or [],
        "port_exclude": body.get("port_exclude") or [],
        "boxes_only": bool(body.get("boxes_only")),
        "palette": body.get("palette") or {},
    }
    if hierarchical:
        options["include"] = None
    else:
        include = body.get("include") or []
        if not include:
            raise ValueError("请至少勾选一个节点")
        options["include"] = include
    return options


def make_handler():
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
                self._send_json(document_api_payload(self.server))
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
            if path == "/api/document":
                try:
                    raw = self._read_body()
                    body = json.loads(raw.decode("utf-8") or "{}")
                    doc, filename = _parse_open_body(body)
                except ValueError as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 400)
                    return
                except json.JSONDecodeError:
                    self._send_json({"ok": False, "error": "JSON 无效"}, 400)
                    return
                try:
                    store_schematic_source(self.server, doc, filename)
                except ValueError as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 400)
                    return
                self._send_json(document_api_payload(self.server))
                return
            if path != "/api/draw":
                self._send_json({"ok": False, "error": "Not Found"}, 404)
                return
            if getattr(self.server, "schematic_document", None) is None:
                self._send_json({"ok": False, "error": "请先打开电路图 JSON"}, 400)
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
            hierarchical = getattr(self.server, "schematic_view_mode", "flat") == "hierarchical"
            try:
                options = _draw_options(body, hierarchical)
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, 400)
                return
            filename = getattr(self.server, "schematic_filename", "") or "graph.json"
            view_module = getattr(self.server, "schematic_view_module", "") or ""
            expanded_paths = set()
            if hierarchical:
                view_module = body.get("view_module") or view_module
                raw_paths = body.get("expanded_paths")
                if raw_paths is not None:
                    if not isinstance(raw_paths, list):
                        self._send_json({"ok": False, "error": "expanded_paths 须为数组"}, 400)
                        return
                    expanded_paths = {str(item) for item in raw_paths if item}
                merged = getattr(self.server, "schematic_merged", None)
                if merged is None:
                    self._send_json({"ok": False, "error": "缺少 module 库"}, 400)
                    return
                try:
                    document = elaborate_view(merged, view_module, expanded_paths)
                except ValueError as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 400)
                    return
            else:
                document = self.server.schematic_document
            try:
                svg = draw(document, options)
            except Exception as exc:
                self._send_json({"ok": False, "error": "出图失败: %s" % exc}, 500)
                return
            stem = os.path.splitext(filename)[0] or "graph"
            payload = {"ok": True, "filename": stem + ".svg", "svg": svg}
            try:
                payload["drawio"] = svg_to_drawio(svg, title=stem)
                payload["drawio_filename"] = stem + ".drawio"
            except (RuntimeError, ValueError) as exc:
                payload["drawio"] = None
                payload["drawio_error"] = str(exc)
            if hierarchical:
                payload["tree"] = tree_of(document["root"])
                payload["view_module"] = view_module
                payload["expanded_paths"] = sorted(expanded_paths)
            self._send_json(payload)

    return Handler


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, handler, log_to_stderr=False):
        self.log_to_stderr = log_to_stderr
        self.schematic_view_mode = "flat"
        self.schematic_merged = None
        self.schematic_view_module = ""
        self.schematic_document = None
        self.schematic_filename = ""
        ThreadingHTTPServer.__init__(self, server_address, handler)


def serve(view_context=None, filename="", host="127.0.0.1", port=8765, verbose=False):
    server = QuietThreadingHTTPServer(
        (host, port), make_handler(), log_to_stderr=verbose,
    )
    if view_context:
        if view_context.get("mode") == "hierarchical":
            _set_hierarchical(
                server,
                view_context["merged"],
                view_context["view_module"],
                filename,
            )
        elif view_context.get("mode") == "flat":
            _set_flat(server, view_context["document"], filename)
    print("Schematic: http://%s:%s" % (host, port), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
