"""
Generated placeholder artwork for catalogue products.

Real photography is the goal; until it exists, a product with no image would
render as a broken tile in the app. These cards are deliberately designed rather
than grey boxes: a category-coloured ground, the category name, and the product
name set large. They are generated at seed time, so no binaries live in the repo,
and any one of them is replaced the moment someone uploads a real photo.
"""

import io
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont

# Generated art is written under this prefix so it can always be told apart from
# a real photo uploaded through Django admin, which lands directly in products/.
GENERATED_PREFIX = "products/generated/"

WIDTH, HEIGHT = 800, 600

# Ground and accent per category, kept within an earthy agricultural range
PALETTE = {
    "seed": ("#2f6d3a", "#4c9455"),
    "fertilizer": ("#6b4423", "#8c5c33"),
    "crop_protection": ("#1f5f6b", "#2f8494"),
    "tool": ("#4a4f57", "#6b7280"),
    "irrigation": ("#1d5a7a", "#2b7ca3"),
    "protective_equipment": ("#7a4a1d", "#a3652b"),
    "grain": ("#8a6a1f", "#b08c2e"),
    "tuber": ("#6d4a2f", "#8f6440"),
    "legume": ("#3f6b2f", "#578f42"),
    "vegetable": ("#2c7a4b", "#3da066"),
    "fruit": ("#9a5a1f", "#c2762c"),
    "cash_crop": ("#5a3a6b", "#78508f"),
}
FALLBACK = ("#2e7d32", "#4c9455")

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def _font(size):
    """Best available bold face, falling back to PIL's bitmap font off-container."""
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(draw, text, font, max_width):
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def build_placeholder(name: str, category: str, category_label: str) -> ContentFile:
    """Render one product card and return it ready to assign to an ImageField."""
    ground, accent = PALETTE.get(category, FALLBACK)

    image = Image.new("RGB", (WIDTH, HEIGHT), ground)
    draw = ImageDraw.Draw(image)

    # a soft diagonal wedge so the card reads as designed, not as a failure state
    draw.polygon([(0, HEIGHT), (WIDTH, HEIGHT * 0.45), (WIDTH, HEIGHT)], fill=accent)
    draw.ellipse(
        [WIDTH - 190, -110, WIDTH + 110, 190],
        fill=accent,
    )

    margin = 56
    label_font = _font(24)
    draw.text((margin, margin), category_label.upper(), font=label_font, fill="#ffffff")
    draw.line(
        [(margin, margin + 44), (margin + 64, margin + 44)], fill="#ffffff", width=3
    )

    # shrink the title until the wrapped name fits comfortably
    for size in (68, 60, 52, 44, 38, 32):
        title_font = _font(size)
        lines = _wrap(draw, name, title_font, WIDTH - margin * 2)
        if len(lines) <= 3:
            break

    line_height = size + 12
    y = HEIGHT - margin - line_height * len(lines)
    for line in lines:
        draw.text((margin, y), line, font=title_font, fill="#ffffff")
        y += line_height

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=86, optimize=True)
    return ContentFile(buffer.getvalue())
