"""Image extraction + compression handler.

The parser populates ``ImageNode.image_data`` with raw bytes pulled from
``word/media/``. This handler compresses any image whose decoded surface
exceeds ~2 MB and re-encodes to keep the output zip lean. The compressed
bytes are written back to the ImageNode and also returned in a filename →
bytes dict that the packager writes into ``/figures``.

Owner: P4. Reference: bible §2 Layer 4 + team distribution P4 note 3.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Dict, List

from PIL import Image, UnidentifiedImageError

from app.converter.ir_schema import ImageNode

logger = logging.getLogger(__name__)

_SIZE_BUDGET_BYTES = 2 * 1024 * 1024
_MAX_DIM = 1600


def _maybe_compress(data: bytes) -> bytes:
    if len(data) <= _SIZE_BUDGET_BYTES:
        return data
    try:
        img = Image.open(BytesIO(data))
    except UnidentifiedImageError:
        logger.warning("Could not decode image; passing through original bytes.")
        return data

    img.thumbnail((_MAX_DIM, _MAX_DIM), Image.LANCZOS)

    out = BytesIO()
    fmt = (img.format or "PNG").upper()
    if fmt in ("JPEG", "JPG"):
        img.convert("RGB").save(out, format="JPEG", quality=85, optimize=True)
    elif fmt == "PNG":
        img.save(out, format="PNG", optimize=True)
    else:
        img.convert("RGBA").save(out, format="PNG", optimize=True)
    return out.getvalue()


def process_images(nodes: List[ImageNode]) -> Dict[str, bytes]:
    """Compress in-place and return a {filename: bytes} dict for packaging."""
    out: Dict[str, bytes] = {}
    for node in nodes:
        original_len = len(node.image_data)
        compressed = _maybe_compress(node.image_data)
        node.image_data = compressed
        if compressed != node.image_data:  # pragma: no cover - identity always equal here
            pass
        if original_len > _SIZE_BUDGET_BYTES and not node.filename.lower().endswith(
            (".png", ".jpg", ".jpeg")
        ):
            node.filename = node.filename.rsplit(".", 1)[0] + ".png"
        out[node.filename] = compressed
    return out
