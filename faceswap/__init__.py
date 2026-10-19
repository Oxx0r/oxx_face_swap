"""Oxx' FaceSwap – lokaler Face Swap auf Basis von InsightFace."""

from .engine import (
    FaceSwapEngine,
    HEADS_DIR,
    ModelMissingError,
    OUTPUT_DIR,
    annotate_faces,
    list_head_images,
    load_image,
    save_image,
)

__all__ = [
    "FaceSwapEngine",
    "HEADS_DIR",
    "ModelMissingError",
    "OUTPUT_DIR",
    "annotate_faces",
    "list_head_images",
    "load_image",
    "save_image",
]

__version__ = "1.1.0"
