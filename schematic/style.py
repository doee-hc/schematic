"""Palette lookup and edge-color ranking for schematic documents."""


SHAPE_FILL = {
    "box": "#ffffff",
    "reg": "#eee8f8",
    "mux": "#fff3e0",
    "logic": "#e7f6e7",
}
SHAPE_STROKE = {
    "reg": "#6b4ea0",
    "mux": "#c47a1a",
    "logic": "#3d8b40",
}

# Edge color prefers a net swatch over a generic module fill.
# Prefixes are a document convention, not a hardware language.
_SWATCH_RANK = {"clock": 0, "reset": 1, "port": 2}


def pick_swatch(*keys):
    """Prefer clock, then reset, then port. Ignore other prefixes."""
    best = None
    best_rank = 99
    for key in keys:
        if not key:
            continue
        kind = str(key).split(":", 1)[0]
        if kind not in _SWATCH_RANK:
            continue
        score = _SWATCH_RANK[kind]
        if score < best_rank:
            best = key
            best_rank = score
    return best or ""


def darken(color, amount=0.28):
    color = (color or "").strip()
    if not color.startswith("#") or len(color) not in (4, 7):
        return "#222222"
    if len(color) == 4:
        color = "#" + "".join(ch * 2 for ch in color[1:])
    rgb = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c * (1.0 - amount)))) for c in rgb)


def color_for(palette, key, fallback="#ffffff"):
    if not key:
        return fallback
    if palette and key in palette:
        return palette[key]
    return fallback
