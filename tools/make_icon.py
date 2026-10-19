"""Erzeugt assets/icon.ico und assets/copy.png für Oxx' FaceSwap."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# Blitz-Polygon, relativ zu 256x256
BOLT = [
    (150, 18),
    (62, 142),
    (116, 142),
    (94, 240),
    (198, 104),
    (136, 104),
]


def build(size: int) -> Image.Image:
    scale = size / 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    margin = int(6 * scale)
    draw.ellipse(
        (margin, margin, size - margin, size - margin),
        fill=(61, 220, 132, 255),
        outline=(18, 90, 55, 255),
        width=max(1, int(4 * scale)),
    )

    points = [(x * scale, y * scale) for x, y in BOLT]
    draw.polygon(points, fill=(9, 24, 16, 255))
    return image


def build_copy_icon(size: int = 48) -> Image.Image:
    """Kleines Copy-Symbol (zwei Blätter) für den Kopieren-Button."""
    scale = size / 48
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def rect(box, width, alpha):
        draw.rounded_rectangle(
            [int(v * scale) for v in box],
            radius=int(5 * scale),
            outline=(255, 255, 255, alpha),
            width=max(1, int(width * scale)),
        )

    rect((8, 6, 32, 30), 3, 165)
    rect((16, 14, 40, 38), 3, 255)
    return image


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    sizes = [256, 128, 64, 48, 32, 16]
    images = [build(size) for size in sizes]
    icon_path = ASSETS / "icon.ico"
    images[0].save(icon_path, format="ICO", sizes=[(s, s) for s in sizes])
    images[0].save(ASSETS / "icon.png")
    build_copy_icon().save(ASSETS / "copy.png")
    print(f"Icon geschrieben: {icon_path}")
    print(f"Copy-Symbol: {ASSETS / 'copy.png'}")


if __name__ == "__main__":
    main()
