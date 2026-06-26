from __future__ import annotations

import hashlib
import io
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from newsletter_kindle.models import Newsletter

_ASSETS = Path(__file__).parent.parent / "assets" / "fonts"
_W, _H = 1600, 2400


def _seed(date: str) -> int:
    return int(hashlib.md5(date.encode()).hexdigest(), 16) % (2**32)


def _gradient_mesh(draw: ImageDraw.ImageDraw, seed: int) -> None:
    rng = random.Random(seed)
    hue = rng.randint(0, 360)

    def hsv_to_rgb(h: int, s: float, v: float) -> tuple[int, int, int]:
        h_f = h / 60
        i = int(h_f)
        f = h_f - i
        p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
        sectors = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]
        r, g, b = sectors[i % 6]
        return int(r * 255), int(g * 255), int(b * 255)

    c1 = hsv_to_rgb(hue, 0.65, 0.85)
    c2 = hsv_to_rgb((hue + 40) % 360, 0.55, 0.60)
    c3 = hsv_to_rgb((hue + 200) % 360, 0.70, 0.25)

    # Gradient backdrop
    for y in range(_H):
        t = y / _H
        r = int(c1[0] * (1 - t) + c2[0] * t)
        g = int(c1[1] * (1 - t) + c2[1] * t)
        b = int(c1[2] * (1 - t) + c2[2] * t)
        draw.line([(0, y), (_W, y)], fill=(r, g, b))

    # Geometric mesh accents
    for _ in range(12):
        x0 = rng.randint(-100, _W + 100)
        y0 = rng.randint(-100, int(_H * 0.65))
        x1 = x0 + rng.randint(100, 500)
        y1 = y0 + rng.randint(100, 500)
        alpha = rng.randint(15, 45)
        draw.rectangle([x0, y0, x1, y1], outline=(*c3, alpha), width=2)

    # Diagonal accent lines
    for i in range(6):
        offset = rng.randint(0, _W)
        draw.line(
            [(offset, 0), (offset - int(_H * 0.4), int(_H * 0.65))],
            fill=(*c3, 25),
            width=1,
        )

    return c3  # type: ignore[return-value]


def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = _ASSETS / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def generate_cover(newsletter: Newsletter) -> bytes:
    seed = _seed(newsletter.date)
    img = Image.new("RGB", (_W, _H), (20, 20, 30))
    draw = ImageDraw.Draw(img, "RGBA")

    accent_color = _gradient_mesh(draw, seed)

    # Dark bottom panel
    panel_top = int(_H * 0.62)
    draw.rectangle([0, panel_top, _W, _H], fill=(15, 15, 22))

    # Colored left spine stripe
    rng = random.Random(seed)
    hue = rng.randint(0, 360)
    stripe_color = _hue_to_rgb(hue)
    draw.rectangle([0, panel_top, 8, _H], fill=stripe_color)

    # Publisher name — small all-caps above title
    font_small = _load_font("Inter-Medium.ttf", 38)
    source_display = newsletter.source_name.upper()
    draw.text((60, panel_top + 55), source_display, fill=(180, 180, 200), font=font_small)

    # Title / main newsletter name — large bold
    font_title = _load_font("Inter-Bold.ttf", 130)
    title_prefix = newsletter.title.split(" — ")[0]
    draw.text((55, panel_top + 105), title_prefix, fill=(255, 255, 255), font=font_title)

    # Date — monospace, below title
    font_date = _load_font("JetBrainsMono-Regular.ttf", 52)
    draw.text((60, panel_top + 270), newsletter.date, fill=(160, 160, 180), font=font_date)

    # Divider line
    draw.line([(55, panel_top + 345), (_W - 55, panel_top + 345)], fill=(60, 60, 80), width=1)

    # Headline peek — first 3 stories
    font_story = _load_font("Inter-Regular.ttf", 38)
    stories: list[str] = []
    for section in newsletter.sections:
        for story in section.stories:
            if len(stories) >= 3:
                break
            stories.append(story.title[:75] + ("…" if len(story.title) > 75 else ""))
        if len(stories) >= 3:
            break

    y_offset = panel_top + 370
    for i, headline in enumerate(stories):
        draw.text((60, y_offset), f"• {headline}", fill=(130, 130, 160), font=font_story)
        y_offset += 58

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()


def _hue_to_rgb(hue: int) -> tuple[int, int, int]:
    h = hue / 60
    x = int(255 * (1 - abs(h % 2 - 1)))
    sectors = [
        (255, x, 0), (x, 255, 0), (0, 255, x),
        (0, x, 255), (x, 0, 255), (255, 0, x),
    ]
    return sectors[int(h) % 6]
