import os
from typing import List

from PIL import Image, ImageDraw, ImageFont

from app.config import TEMPLATE_PATH, CERTIFICATES_DIR

_FONT_CANDIDATES_BOLD = [
    "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
]
_FONT_CANDIDATES_REGULAR = [
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
]

# White writing area inside the template (pixels, template is 1200x896)
TEXT_BOX = (270, 250, 930, 670)
TEXT_COLOR = (40, 40, 60)
ACCENT_COLOR = (20, 60, 110)


def _load_font(candidates: List[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> List[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_centered(draw, text, font, y, color, box_left, box_right) -> int:
    """Draws one line centered in the box; returns the y position after it."""
    width = draw.textlength(text, font=font)
    x = box_left + ((box_right - box_left) - width) / 2
    draw.text((x, y), text, font=font, fill=color)
    bbox = font.getbbox(text)
    return y + (bbox[3] - bbox[1]) + 18


def generate_certificate_pdf(student_name: str, school_name: str, output_name: str) -> str:
    """
    Writes the certificate text on the template and saves it as a PDF in the
    public/certificates folder. Returns the absolute path of the saved file.
    """
    os.makedirs(CERTIFICATES_DIR, exist_ok=True)

    image = Image.open(TEMPLATE_PATH).convert("RGB")
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = TEXT_BOX
    max_width = right - left

    title_font = _load_font(_FONT_CANDIDATES_BOLD, 54)
    name_font = _load_font(_FONT_CANDIDATES_BOLD, 46)
    body_font = _load_font(_FONT_CANDIDATES_REGULAR, 30)

    body_top = f"This is to certify that Mr/Ms"
    body_mid = f"of {school_name}"
    body_bottom = (
        "has taken part in the drawing competition "
        "and has successfully completed the competition."
    )

    # Measure total height first so the block can be vertically centered
    blocks = [
        ("CERTIFICATE", title_font, ACCENT_COLOR),
        ("OF PARTICIPATION", body_font, ACCENT_COLOR),
        (body_top, body_font, TEXT_COLOR),
        (student_name, name_font, ACCENT_COLOR),
        (body_mid, body_font, TEXT_COLOR),
    ]
    lines = []
    for text, font, color in blocks:
        for line in _wrap(draw, text, font, max_width):
            lines.append((line, font, color))
    for line in _wrap(draw, body_bottom, body_font, max_width):
        lines.append((line, body_font, TEXT_COLOR))

    total_height = sum((f.getbbox(t)[3] - f.getbbox(t)[1]) + 18 for t, f, _ in lines)
    y = top + max(0, ((bottom - top) - total_height) / 2)

    for text, font, color in lines:
        y = _draw_centered(draw, text, font, y, color, left, right)

    output_path = os.path.join(CERTIFICATES_DIR, f"{output_name}.pdf")
    image.save(output_path, "PDF", resolution=150.0)
    return output_path
