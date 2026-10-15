"""Convert schematic SVG markup to draw.io XML (via svg-to-drawio)."""


def svg_to_drawio(svg_text, *, title="diagram"):
    """Return uncompressed `.drawio` XML for the given SVG string."""
    try:
        from svg_to_drawio import convert_svg_string
    except ImportError as exc:
        raise RuntimeError(
            "draw.io 导出需要 Python 3.11+ 并安装：pip install 'svg-to-drawio>=3.9'"
        ) from exc
    if not (svg_text or "").strip():
        raise ValueError("SVG 为空")
    return convert_svg_string(svg_text, title=title or "diagram")
