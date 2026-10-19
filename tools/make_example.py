"""Erzeugt docs/beispiel.png (Vorher/Nachher-Demo aus den Beispielbildern)."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from faceswap.engine import FaceSwapEngine, load_image, save_image  # noqa: E402


def main() -> None:
    source_path = ROOT / "samples" / "t1.jpg"
    target_path = ROOT / "samples" / "gruppe.jpg"
    if not target_path.is_file():
        target_path = source_path

    engine = FaceSwapEngine()
    engine.load()

    source_image = load_image(source_path)
    source_faces = engine.detect(source_image)
    target_image = load_image(target_path)
    target_faces = engine.detect(target_image)

    source_face = engine.pick_source_face(source_faces, 1)
    result = engine.swap_faces(target_image, target_faces, source_face, range(len(target_faces)))

    height = 320
    panels = []
    for label, bgr in [("Vorher", target_image), ("Nachher", result)]:
        pil = Image.fromarray(bgr[:, :, ::-1])
        width = int(pil.width * height / pil.height)
        panels.append((label, pil.resize((width, height), Image.LANCZOS)))

    paper = Image.new("RGB", (sum(p[1].width for p in panels) + 24, height + 34), (17, 20, 26))
    draw = ImageDraw.Draw(paper)
    x = 8
    for label, pil in panels:
        paper.paste(pil, (x, 26))
        draw.text((x + 4, 8), label, fill=(230, 236, 245))
        x += pil.width + 8

    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    out = docs / "beispiel.png"
    paper.save(out)
    print("Beispielbild:", out)


if __name__ == "__main__":
    main()
