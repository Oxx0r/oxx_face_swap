"""Kern-Engine: Gesichtserkennung, Embeddings und Face Swap.

Die eigentliche Arbeit machen die InsightFace-Modelle:
  * buffalo_l  – SCRFD-Detektor + ArcFace-Embedding
  * inswapper_128.onnx – eigentliches Swap-Modell

Alles läuft lokal. Es werden keine Bilder hochgeladen.
"""

from __future__ import annotations

import contextlib
import io
import threading
import warnings
from pathlib import Path
from typing import Iterable, Sequence

import cv2
import numpy as np
from PIL import Image, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
BUFFALO_DIR = MODELS_DIR / "buffalo_l"
INSWAPPER_FILE = MODELS_DIR / "inswapper_128.onnx"
OUTPUT_DIR = PROJECT_ROOT / "output"
HEADS_DIR = PROJECT_ROOT / "heads"

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


class ModelMissingError(RuntimeError):
    """Wird geworfen, wenn die ONNX-Modelle nicht gefunden werden."""


class FaceSwapEngine:
    """Lazy geladene Face-Swap-Pipeline (CPU oder CUDA)."""

    def __init__(self, device: str = "auto", det_size: int = 640) -> None:
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("device muss 'auto', 'cpu' oder 'cuda' sein")
        self.device = device
        self.det_size = int(det_size)
        self._app = None
        self._swapper = None
        self._lock = threading.RLock()
        self.providers: list[str] = []
        self.active_device = "CPU"

    # ------------------------------------------------------------------ Setup
    def load(self) -> None:
        """Lädt Detektor, Recognition- und Swap-Modell (einmalig)."""
        with self._lock:
            if self._app is not None and self._swapper is not None:
                return

            self._check_models()

            # InsightFace/onnxruntime sind im Normalbetrieb sehr gesprächig.
            warnings.filterwarnings("ignore", category=FutureWarning)
            suggestions = io.StringIO()
            noise = contextlib.redirect_stdout(suggestions)

            import onnxruntime

            onnxruntime.set_default_logger_severity(3)
            available = onnxruntime.get_available_providers()

            if self.device == "cuda" and "CUDAExecutionProvider" not in available:
                raise RuntimeError(
                    "CUDA wurde angefordert, ist aber nicht verfügbar. "
                    "Installiere onnxruntime-gpu (siehe README) oder nutze --device cpu."
                )

            use_cuda = (
                self.device == "cuda"
                or (self.device == "auto" and "CUDAExecutionProvider" in available)
            )
            if use_cuda:
                self.providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                self.active_device = "CUDA"
            else:
                self.providers = ["CPUExecutionProvider"]
                self.active_device = "CPU"

            with noise:
                from insightface.app import FaceAnalysis
                from insightface.model_zoo import get_model

                app = FaceAnalysis(
                    name=str(BUFFALO_DIR),
                    providers=self.providers,
                    allowed_modules=["detection", "recognition"],
                )
                app.prepare(
                    ctx_id=0 if use_cuda else -1,
                    det_size=(self.det_size, self.det_size),
                )

                swapper = get_model(str(INSWAPPER_FILE), providers=self.providers)
                if swapper is None:
                    raise RuntimeError(
                        "inswapper_128.onnx konnte nicht geladen werden. "
                        "Ist die Datei vollständig heruntergeladen?"
                    )

            self._app = app
            self._swapper = swapper

    @staticmethod
    def _check_models() -> None:
        missing = []
        if not BUFFALO_DIR.is_dir() or not any(BUFFALO_DIR.glob("*.onnx")):
            missing.append(str(BUFFALO_DIR))
        if not INSWAPPER_FILE.is_file():
            missing.append(str(INSWAPPER_FILE))
        if missing:
            raise ModelMissingError(
                "Folgende Modelle fehlen:\n  - "
                + "\n  - ".join(missing)
                + "\n\nStarte einmalig:  .\\install.ps1"
            )

    @property
    def ready(self) -> bool:
        return self._app is not None and self._swapper is not None

    # -------------------------------------------------------------- Detection
    def _detect_raw(self, image_bgr: np.ndarray) -> list:
        with self._lock:
            return list(self._app.get(image_bgr))

    def detect(self, image_bgr: np.ndarray) -> list:
        """Erkennt Gesichter und liefert sie von links nach rechts sortiert.

        Ist ein Gesicht so groß, dass es das ganze Bild füllt, erkennt der
        Detektor es nicht zuverlässig. Deshalb wird notfalls ein Rand ergänzt
        und die Koordinaten danach wieder zurückgerechnet.
        """
        self.load()
        for pad_ratio in (0.0, 0.35, 1.0):
            if pad_ratio == 0.0:
                canvas = image_bgr
                offset = 0
            else:
                offset = int(max(image_bgr.shape[:2]) * pad_ratio)
                canvas = cv2.copyMakeBorder(
                    image_bgr,
                    offset,
                    offset,
                    offset,
                    offset,
                    cv2.BORDER_REPLICATE,
                )

            faces = self._detect_raw(canvas)
            if not faces:
                continue

            if offset:
                for face in faces:
                    face.bbox = np.asarray(face.bbox, dtype=np.float32) - offset
                    face.kps = np.asarray(face.kps, dtype=np.float32) - offset

            faces.sort(key=lambda face: float(face.bbox[0]))
            return faces
        return []

    def pick_source_face(self, faces: Sequence, index: int | None = None):
        """Wählt das Spender-Gesicht: standardmäßig das größte."""
        if not faces:
            raise ValueError("Im Quellbild wurde kein Gesicht gefunden.")
        if index is None:
            return max(
                faces,
                key=lambda face: float(
                    (face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1])
                ),
            )
        if index < 1 or index > len(faces):
            raise ValueError(
                f"Quellgesicht {index} existiert nicht (gefunden: {len(faces)})."
            )
        return faces[index - 1]

    # ------------------------------------------------------------------- Swap
    def swap_faces(
        self,
        image_bgr: np.ndarray,
        target_faces: Sequence,
        source_face,
        indices: Iterable[int],
    ) -> np.ndarray:
        """Ersetzt die ausgewählten Zielgesichter durch das Quellgesicht."""
        self.load()
        result = image_bgr.copy()
        with self._lock:
            for index in indices:
                result = self._swapper.get(
                    result,
                    target_faces[index],
                    source_face,
                    paste_back=True,
                )
        return result


# --------------------------------------------------------------------- Bilder
def load_image(path: str | Path) -> np.ndarray:
    """Liest ein Bild EXIF-korrekt und Unicode-sicher als BGR-Array."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Bild nicht gefunden: {path}")
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode in {"RGBA", "LA"}:
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[-1])
            image = background
        else:
            image = image.convert("RGB")
        rgb = np.asarray(image)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def save_image(image_bgr: np.ndarray, path: str | Path, quality: int = 95) -> Path:
    """Speichert ein BGR-Array als Bild und legt Ordner automatisch an."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(rgb)
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        image.save(path, quality=quality, subsampling=0)
    else:
        image.save(path)
    return path


def unique_output_path(target: str | Path, suffix: str = "_swapped") -> Path:
    """Erzeugt output/<name>_swapped.<ext>, ohne vorhandene Dateien zu überschreiben."""
    target = Path(target)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidate = OUTPUT_DIR / f"{target.stem}{suffix}{target.suffix or '.jpg'}"
    counter = 2
    while candidate.exists():
        candidate = OUTPUT_DIR / f"{target.stem}{suffix}_{counter}{target.suffix or '.jpg'}"
        counter += 1
    return candidate


def list_head_images() -> list[Path]:
    """Listet alle Bilder im Ordner heads/ (inkl. Unterordner), alphabetisch."""
    if not HEADS_DIR.is_dir():
        return []
    return sorted(
        path
        for path in HEADS_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


# ------------------------------------------------------------------ Overlays
def annotate_faces(
    image_bgr: np.ndarray,
    faces: Sequence,
    selected: Iterable[int] | None = None,
) -> np.ndarray:
    """Zeichnet Gesichtsboxen mit Nummern ins Bild (für die Vorschau)."""
    output = image_bgr.copy()
    height, width = output.shape[:2]
    thickness = max(2, round(min(width, height) / 400))
    selected_set = set(selected) if selected is not None else set(range(len(faces)))

    for index, face in enumerate(faces):
        x1, y1, x2, y2 = (int(value) for value in face.bbox)
        color = (80, 200, 90) if index in selected_set else (90, 150, 230)
        cv2.rectangle(output, (x1, y1), (x2, y2), color, thickness, cv2.LINE_AA)
        label = f"{index + 1}"
        font_scale = max(0.6, min(width, height) / 900)
        (text_width, text_height), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_DUPLEX, font_scale, thickness
        )
        top = max(0, y1 - text_height - baseline - 8)
        cv2.rectangle(
            output,
            (x1, top),
            (x1 + text_width + 12, y1),
            color,
            cv2.FILLED,
        )
        cv2.putText(
            output,
            label,
            (x1 + 6, y1 - baseline - 3),
            cv2.FONT_HERSHEY_DUPLEX,
            font_scale,
            (20, 25, 30),
            thickness,
            cv2.LINE_AA,
        )
    return output


def parse_face_selection(spec: str | int, count: int) -> list[int]:
    """Parst 'all', '1', '1,3' oder '1-3' in 0-basierte Indizes."""
    if count <= 0:
        return []
    if isinstance(spec, int):
        spec = str(spec)
    spec = spec.strip().lower()
    if spec in {"all", "alle", "*"}:
        return list(range(count))

    indices: list[int] = []
    for part in spec.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            indices.extend(range(int(start), int(end) + 1))
        else:
            indices.append(int(part))

    for index in indices:
        if index < 1 or index > count:
            raise ValueError(
                f"Gesicht {index} existiert nicht (gefunden: {count})."
            )
    # Reihenfolge beibehalten, Duplikate entfernen
    return list(dict.fromkeys(index - 1 for index in indices))
