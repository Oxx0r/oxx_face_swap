"""Kommandozeilen-Version von Oxx' FaceSwap.

Beispiele:
    python faceswap_cli.py --source spender.jpg --target gruppe.jpg
    python faceswap_cli.py --source spender.jpg --target a.jpg b.jpg -o results
    python faceswap_cli.py --source spender.jpg --target gruppe.jpg --face 2
    python faceswap_cli.py --target gruppe.jpg --list
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from faceswap.engine import (
    FaceSwapEngine,
    ModelMissingError,
    SUPPORTED_EXTENSIONS,
    load_image,
    parse_face_selection,
    save_image,
    unique_output_path,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="faceswap_cli.py",
        description="Ersetzt Gesichter in Bildern durch ein Spender-Gesicht (lokal, offline).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--source", "-s", help="Bild mit dem Spender-Gesicht")
    parser.add_argument(
        "--target",
        "-t",
        nargs="+",
        required=True,
        help="Zielbild(er), in denen getauscht wird",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Ausgabedatei (ein Bild) oder Ausgabeordner (mehrere Bilder)",
    )
    parser.add_argument(
        "--face",
        "-f",
        default="all",
        help="Zielgesichter: 'all', '1', '1,3' oder '1-3' (Standard: all)",
    )
    parser.add_argument(
        "--source-face",
        type=int,
        default=None,
        help="Nummer des Spender-Gesichts (Standard: größtes Gesicht)",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        default="auto",
        help="Rechengerät (Standard: auto)",
    )
    parser.add_argument(
        "--det-size",
        type=int,
        default=640,
        help="Detektor-Auflösung, 640 ist ein guter Standard (höher = genauer, langsamer)",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=95,
        help="JPEG-Qualität 1-100 (Standard: 95)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Nur gefundene Gesichter in den Zielbildern auflisten",
    )
    return parser


def fail(message: str, code: int = 1) -> int:
    print(f"\nFehler: {message}", file=sys.stderr)
    return code


def print_faces(path: Path, faces: list) -> None:
    print(f"\n{path.name}: {len(faces)} Gesicht(er)")
    for index, face in enumerate(faces, start=1):
        x1, y1, x2, y2 = (int(value) for value in face.bbox)
        print(
            f"  {index}: x={x1}, y={y1}, Breite={x2 - x1}, Höhe={y2 - y1}, "
            f"Score={float(face.det_score):.2f}"
        )


def resolve_outputs(
    targets: list[Path], output: str | None
) -> list[Path]:
    if output is None:
        return [unique_output_path(target) for target in targets]

    output_path = Path(output)
    multiple = len(targets) > 1
    if multiple:
        if output_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            raise ValueError(
                "Bei mehreren Zielbildern muss --output ein Ordner sein."
            )
        output_path.mkdir(parents=True, exist_ok=True)
        return [
            output_path / f"{target.stem}_swapped{target.suffix or '.jpg'}"
            for target in targets
        ]

    if output_path.is_dir() or output_path.suffix == "":
        output_path.mkdir(parents=True, exist_ok=True)
        target = targets[0]
        return [output_path / f"{target.stem}_swapped{target.suffix or '.jpg'}"]
    return [output_path]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    targets = [Path(target) for target in args.target]
    missing_targets = [str(path) for path in targets if not path.is_file()]
    if missing_targets:
        return fail("Zielbild nicht gefunden: " + ", ".join(missing_targets))

    if not args.list and not args.source:
        return fail("Bitte --source <spender.jpg> angeben (oder --list nutzen).")
    if args.source and not Path(args.source).is_file():
        return fail(f"Quellbild nicht gefunden: {args.source}")

    try:
        outputs = resolve_outputs(targets, args.output)
    except ValueError as error:
        return fail(str(error))

    engine = FaceSwapEngine(device=args.device, det_size=args.det_size)
    try:
        print("Lade Modelle ...", end="", flush=True)
        started = time.perf_counter()
        engine.load()
        print(
            f" fertig ({engine.active_device}, {time.perf_counter() - started:.1f}s)"
        )

        if args.list:
            for target in targets:
                faces = engine.detect(load_image(target))
                print_faces(target, faces)
            return 0

        source_image = load_image(args.source)
        source_faces = engine.detect(source_image)
        if not source_faces:
            return fail("Im Quellbild wurde kein Gesicht gefunden.")
        if args.source_face is not None and not (
            1 <= args.source_face <= len(source_faces)
        ):
            return fail(
                f"Quellgesicht {args.source_face} existiert nicht "
                f"(gefunden: {len(source_faces)})."
            )
        source_face = engine.pick_source_face(source_faces, args.source_face)
        print_faces(Path(args.source), source_faces)

        for target_path, output_path in zip(targets, outputs):
            print(f"\nVerarbeite {target_path.name} ...")
            image = load_image(target_path)
            faces = engine.detect(image)
            if not faces:
                print("  Übersprungen: kein Gesicht gefunden.")
                continue
            print_faces(target_path, faces)

            try:
                indices = parse_face_selection(args.face, len(faces))
            except ValueError as error:
                return fail(str(error))
            if not indices:
                print("  Übersprungen: keine Gesichter ausgewählt.")
                continue

            swap_started = time.perf_counter()
            result = engine.swap_faces(image, faces, source_face, indices)
            duration = time.perf_counter() - swap_started
            saved = save_image(result, output_path, quality=args.quality)
            print(
                f"  {len(indices)} Gesicht(er) getauscht in {duration:.1f}s"
                f" -> {saved}"
            )

        print("\nFertig. ⚡")
        return 0

    except ModelMissingError as error:
        return fail(str(error))
    except RuntimeError as error:
        return fail(str(error))
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
