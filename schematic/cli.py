"""Command line: schematic draw, schematic view."""

import argparse
import sys

from schematic.render import draw_file, load_document
from schematic.server import serve


def _palette_args(items):
    out = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError("配色需要 key=#hex，收到 %s" % item)
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError("配色键为空")
        out[key] = value
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(prog="schematic", description="正交电路图")
    sub = parser.add_subparsers(dest="cmd")

    draw_p = sub.add_parser("draw", help="把 JSON 画成 SVG")
    draw_p.add_argument("json", help="电路图 JSON")
    draw_p.add_argument("-o", "--output", required=True, help="输出 SVG 路径")
    draw_p.add_argument("--include", action="append", default=None, help="只画这些节点 id，可重复")
    draw_p.add_argument("--port-include", action="append", default=None, help="端口 Include 通配，可重复")
    draw_p.add_argument("--port-exclude", action="append", default=None, help="端口 Exclude 通配，可重复")
    draw_p.add_argument("--boxes-only", action="store_true", help="隐藏 mux、reg、logic")
    draw_p.add_argument("--palette", action="append", default=None, help="覆盖配色 key=#hex，可重复")

    view_p = sub.add_parser("view", help="打开交互查看器")
    view_p.add_argument("json", help="电路图 JSON")
    view_p.add_argument("--host", default="127.0.0.1")
    view_p.add_argument("--port", type=int, default=8765)
    view_p.add_argument("--verbose", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "draw":
        options = {"boxes_only": args.boxes_only}
        if args.include:
            options["include"] = args.include
        if args.port_include is not None:
            options["port_include"] = args.port_include
        if args.port_exclude is not None:
            options["port_exclude"] = args.port_exclude
        if args.palette:
            options["palette"] = _palette_args(args.palette)
        try:
            draw_file(args.json, args.output, options)
        except (OSError, ValueError, RuntimeError) as exc:
            print("出图失败: %s" % exc, file=sys.stderr)
            return 1
        print(args.output)
        return 0
    if args.cmd == "view":
        try:
            document = load_document(args.json)
        except (OSError, ValueError) as exc:
            print("无法读取电路图: %s" % exc, file=sys.stderr)
            return 1
        serve(
            document,
            os_name(args.json),
            host=args.host,
            port=args.port,
            verbose=args.verbose,
        )
        return 0
    parser.print_help()
    return 2


def os_name(path):
    import os
    return os.path.basename(path) or "design.json"


if __name__ == "__main__":
    sys.exit(main())
