"""Create one image-only synthetic PAN PDF for OpenRouter OCR smoke tests."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "samples" / "docs" / "synthetic_scan_pan.pdf"


def generate(path: Path = OUTPUT) -> Path:
    """Make an image-only, visibly synthetic page; no real identity data is used."""
    image = Image.new("RGB", (1240, 1754), "#f5f1e7")
    draw = ImageDraw.Draw(image)
    title = ImageFont.load_default(size=48)
    body = ImageFont.load_default(size=38)
    small = ImageFont.load_default(size=28)
    draw.rounded_rectangle((70, 70, 1170, 1684), radius=24, outline="#334155", width=5, fill="#fffdf8")
    draw.text((140, 160), "INCOME TAX DEPARTMENT", font=title, fill="#183153")
    draw.text((140, 310), "PERMANENT ACCOUNT NUMBER", font=body, fill="#283747")
    draw.text((140, 430), "AAAAA0000A", font=title, fill="#111827")
    draw.text((140, 610), "Name: TEST VENDOR PRIVATE LIMITED", font=body, fill="#111827")
    draw.text((140, 760), "SYNTHETIC TEST DOCUMENT", font=body, fill="#b91c1c")
    draw.text((140, 830), "NOT A VALID IDENTITY DOCUMENT", font=body, fill="#b91c1c")
    draw.text((140, 1540), "Generated for PayeeTrail OCR testing only", font=small, fill="#475569")

    png = io.BytesIO()
    image.save(png, format="PNG")
    pdf_stream = io.BytesIO()
    width, height = A4
    page = canvas.Canvas(pdf_stream, pagesize=A4)
    page.drawImage(ImageReader(io.BytesIO(png.getvalue())), 0, 0, width=width, height=height)
    page.save()

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf_stream.getvalue())
    return path


if __name__ == "__main__":
    print(f"Wrote image-only synthetic scan: {generate().relative_to(ROOT)}")
