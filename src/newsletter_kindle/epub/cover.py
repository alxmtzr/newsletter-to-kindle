from __future__ import annotations

import io
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from newsletter_kindle.models import Newsletter

_RGB = tuple[int, int, int]

_ASSETS = Path(__file__).parent.parent / "assets" / "fonts"
_W, _H = 1200, 1800

_PATTERNS = ["geometric", "diagonal", "circles", "grid", "waves"]


def _hue_to_rgb(hue: int) -> _RGB:
    h = hue / 60
    x = int(255 * (1 - abs(h % 2 - 1)))
    sectors = [
        (255, x, 0), (x, 255, 0), (0, 255, x),
        (0, x, 255), (x, 0, 255), (255, 0, x),
    ]
    return sectors[int(h) % 6]


def _hsv_to_rgb(h: int, s: float, v: float) -> _RGB:
    h_f = h / 60
    i = int(h_f)
    f = h_f - i
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    sectors = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]
    r, g, b = sectors[i % 6]
    return int(r * 255), int(g * 255), int(b * 255)


def _draw_gradient(draw: ImageDraw.ImageDraw, c1: _RGB, c2: _RGB) -> None:
    for y in range(_H):
        t = y / _H
        r = int(c1[0] * (1 - t) + c2[0] * t)
        g = int(c1[1] * (1 - t) + c2[1] * t)
        b = int(c1[2] * (1 - t) + c2[2] * t)
        draw.line([(0, y), (_W, y)], fill=(r, g, b))


def _pattern_geometric(draw: ImageDraw.ImageDraw, rng: random.Random, accent: _RGB) -> None:
    for _ in range(14):
        x0 = rng.randint(-100, _W + 100)
        y0 = rng.randint(-100, int(_H * 0.65))
        x1 = x0 + rng.randint(80, 400)
        y1 = y0 + rng.randint(80, 400)
        alpha = rng.randint(60, 110)
        draw.rectangle([x0, y0, x1, y1], outline=(*accent, alpha), width=rng.randint(2, 4))


def _pattern_diagonal(draw: ImageDraw.ImageDraw, rng: random.Random, accent: _RGB) -> None:
    for _ in range(20):
        x = rng.randint(0, _W)
        draw.line(
            [(x, 0), (x - int(_H * 0.5), _H)],
            fill=(*accent, rng.randint(55, 100)),
            width=rng.randint(2, 4),
        )


def _pattern_circles(draw: ImageDraw.ImageDraw, rng: random.Random, accent: _RGB) -> None:
    for _ in range(10):
        cx = rng.randint(0, _W)
        cy = rng.randint(0, int(_H * 0.65))
        r = rng.randint(60, 300)
        alpha = rng.randint(55, 100)
        w = rng.randint(2, 4)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*accent, alpha), width=w)


def _pattern_grid(draw: ImageDraw.ImageDraw, rng: random.Random, accent: _RGB) -> None:
    spacing = rng.randint(80, 160)
    alpha = rng.randint(55, 90)
    for x in range(0, _W, spacing):
        draw.line([(x, 0), (x, int(_H * 0.65))], fill=(*accent, alpha), width=2)
    for y in range(0, int(_H * 0.65), spacing):
        draw.line([(0, y), (_W, y)], fill=(*accent, alpha), width=2)


def _pattern_waves(draw: ImageDraw.ImageDraw, rng: random.Random, accent: _RGB) -> None:
    import math
    for i in range(8):
        y_base = rng.randint(50, int(_H * 0.6))
        amp = rng.randint(20, 80)
        freq = rng.uniform(0.003, 0.01)
        alpha = rng.randint(60, 110)
        points = [(x, int(y_base + amp * math.sin(freq * x + i))) for x in range(0, _W, 4)]
        if len(points) > 1:
            draw.line(points, fill=(*accent, alpha), width=rng.randint(2, 4))


_PATTERN_FNS = {
    "geometric": _pattern_geometric,
    "diagonal": _pattern_diagonal,
    "circles": _pattern_circles,
    "grid": _pattern_grid,
    "waves": _pattern_waves,
}


def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = _ASSETS / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)  # type: ignore[return-value]


def generate_cover(newsletter: Newsletter) -> bytes:
    # Both colour and pattern are fully random each generation
    pattern_rng = random.Random()

    hue = pattern_rng.randint(0, 360)
    # Keep saturation moderate and value high — readable on e-ink Paperwhite
    # Avoid very dark backgrounds (value < 0.55) and overly saturated colours
    sat = pattern_rng.uniform(0.35, 0.65)
    val = pattern_rng.uniform(0.65, 0.90)
    c1 = _hsv_to_rgb(hue, sat, val)
    c2 = _hsv_to_rgb((hue + pattern_rng.randint(30, 60)) % 360, sat * 0.8, val * 0.75)
    accent = _hsv_to_rgb((hue + 180) % 360, sat * 0.6, val * 0.45)

    img = Image.new("RGB", (_W, _H), (20, 20, 30))
    draw = ImageDraw.Draw(img, "RGBA")

    _draw_gradient(draw, c1, c2)

    # Pick a random pattern
    pattern_name = pattern_rng.choice(_PATTERNS)
    _PATTERN_FNS[pattern_name](draw, pattern_rng, accent)

    # Bottom panel — dark but not pitch black, good contrast on e-ink
    panel_top = int(_H * 0.62)
    draw.rectangle([0, panel_top, _W, _H], fill=(28, 28, 36))

    # Thin coloured accent bar at top of panel
    stripe_color = _hue_to_rgb(hue)
    draw.rectangle([0, panel_top, _W, panel_top + 6], fill=stripe_color)

    x = 40  # consistent left margin

    # Main title — single large "TLDR"
    font_title = _load_font("Inter-Bold.ttf", 140)
    draw.text((x, panel_top + 30), "TLDR", fill=(255, 255, 255), font=font_title)

    # Date below title
    font_date = _load_font("JetBrainsMono-Regular.ttf", 52)
    draw.text((x, panel_top + 195), newsletter.date, fill=(160, 160, 180), font=font_date)

    # Divider
    draw.line([(x, panel_top + 270), (_W - x, panel_top + 270)], fill=(55, 55, 70), width=1)

    # Headline peek — first 3 stories, ASCII only
    font_story = _load_font("Inter-Regular.ttf", 34)
    stories: list[str] = []
    for section in newsletter.sections:
        for story in section.stories:
            if len(stories) >= 3:
                break
            clean = story.title.encode("ascii", errors="ignore").decode("ascii").strip()
            if not clean:
                clean = story.title[:55]
            if len(clean) > 52:
                clean = clean[:52].rstrip() + "..."
            stories.append(clean)
        if len(stories) >= 3:
            break

    y_offset = panel_top + 295
    for headline in stories:
        draw.text((x, y_offset), f"- {headline}", fill=(120, 120, 150), font=font_story)
        y_offset += 56

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88, optimize=True)
    return buf.getvalue()
