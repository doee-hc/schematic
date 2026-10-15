"""Command line: schematic draw, schematic view, schematic elaborate."""

import argparse
import sys

from schematic.elaborate import load_schematic, load_view_context, write_document
from schematic.render import draw_file, draw_sources
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


def _add_source_args(parser):
    parser.add_argument("json", nargs="*", help="电路图 JSON，可多个")
    parser.add_argument("-f", dest="filelist", action="append", default=None, help="filelist（// 注释），每行一个 JSON")
    parser.add_argument("-top", dest="top", default=None, help="顶层 module 名（库文档）")


def _draw_options(args):
    options = {"boxes_only": args.boxes_only}
    if args.include:
        options["include"] = args.include
    if args.port_include is not None:
        options["port_include"] = args.port_include
    if args.port_exclude is not None:
        options["port_exclude"] = args.port_exclude
    if args.palette:
        options["palette"] = _palette_args(args.palette)
    return options


def _require_sources(args):
    if not args.json and not args.filelist:
        raise ValueError("需要至少一个 JSON 路径或 -f filelist")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="schematic", description="正交电路图")
    sub = parser.add_subparsers(dest="cmd")

    draw_p = sub.add_parser("draw", help="把 JSON 画成 SVG")
    _add_source_args(draw_p)
    draw_p.add_argument("-o", "--output", required=True, help="输出 SVG 路径")
    draw_p.add_argument("--include", action="append", default=None, help="只画这些节点 id，可重复")
    draw_p.add_argument("--port-include", action="append", default=None, help="端口 Include 通配，可重复")
    draw_p.add_argument("--port-exclude", action="append", default=None, help="端口 Exclude 通配，可重复")
    draw_p.add_argument("--boxes-only", action="store_true", help="隐藏 mux、reg、logic、and、or、xor、buf、icg")
    draw_p.add_argument("--palette", action="append", default=None, help="覆盖配色 key=#hex，可重复")

    view_p = sub.add_parser("view", help="打开交互查看器")
    _add_source_args(view_p)
    view_p.add_argument("--host", default="127.0.0.1")
    view_p.add_argument("--port", type=int, default=8765)
    view_p.add_argument("--verbose", action="store_true")

    elab_p = sub.add_parser("elaborate", help="合并库并展开为经典 JSON")
    _add_source_args(elab_p)
    elab_p.add_argument("-o", "--output", required=True, help="输出 JSON 路径")

    args = parser.parse_args(argv)
    if args.cmd == "draw":
        try:
            _require_sources(args)
            options = _draw_options(args)
            if len(args.json) == 1 and not args.filelist and not args.top:
                draw_file(args.json[0], args.output, options)
            else:
                draw_sources(args.json, args.output, options, filelists=args.filelist, top=args.top)
        except (OSError, ValueError, RuntimeError) as exc:
            print("出图失败: %s" % exc, file=sys.stderr)
            return 1
        print(args.output)
        return 0
    if args.cmd == "view":
        view_context = None
        filename = ""
        if args.json or args.filelist:
            try:
                _require_sources(args)
                view_context = load_view_context(
                    args.json, filelists=args.filelist, top=args.top,
                )
                filename = os_name(args.json[-1] if args.json else args.filelist[-1])
            except (OSError, ValueError) as exc:
                print("无法读取电路图: %s" % exc, file=sys.stderr)
                return 1
        serve(
            view_context=view_context,
            filename=filename,
            host=args.host,
            port=args.port,
            verbose=args.verbose,
        )
        return 0
    if args.cmd == "elaborate":
        try:
            _require_sources(args)
            document = load_schematic(args.json, filelists=args.filelist, top=args.top)
            write_document(args.output, document)
        except (OSError, ValueError) as exc:
            print("展开失败: %s" % exc, file=sys.stderr)
            return 1
        print(args.output)
        return 0
    parser.print_help()
    return 2


def os_name(path):
    import os
    return os.path.basename(path) or "design.json"


if __name__ == "__main__":
    sys.exit(main())
