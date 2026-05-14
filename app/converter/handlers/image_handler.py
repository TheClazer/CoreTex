"""Image extraction + compression handler.

The parser populates ``ImageNode.image_data`` with raw bytes pulled from
``word/media/``. This handler compresses any image whose decoded surface
exceeds ~2 MB and re-encodes to keep the output zip lean. The compressed
bytes are written back to the ImageNode and also returned in a filename →
bytes dict that the packager writes into ``/figures``.

Hardening:
* Pillow's ``MAX_IMAGE_PIXELS`` is lowered to 40 megapixels and the
  default warning is upgraded to a hard error, so decompression-bomb
  PNG/TIFFs (e.g. a 2 MB zip-compressed 50000×50000 file) raise instead
  of allocating multiple GB of RAM.
* EXIF orientation tags and ICC colour profiles are preserved on re-encode.
"""

from __future__ import annotations

import logging
import warnings
from io import BytesIO
from typing import Dict, List

from PIL import Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError, DecompressionBombWarning

from app.converter.ir_schema import ImageNode

logger = logging.getLogger(__name__)

# Decompression-bomb hardening — fail closed at 40 MP. A legitimate paper
# figure rarely exceeds 12 MP (4000×3000).
Image.MAX_IMAGE_PIXELS = 40_000_000
warnings.simplefilter("error", DecompressionBombWarning)

_SIZE_BUDGET_BYTES = 2 * 1024 * 1024
_MAX_DIM = 1600


def _safe_open(data: bytes) -> Image.Image | None:
    try:
        img = Image.open(BytesIO(data))
        # Force a verify pass so malformed headers fail here, not deeper.
        img.verify()
        # verify() consumes the stream; reopen for real use.
        return Image.open(BytesIO(data))
    except (UnidentifiedImageError, DecompressionBombError, DecompressionBombWarning) as e:
        logger.warning("Rejecting image (%s); passing original bytes through.", type(e).__name__)
        return None
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Pillow refused to open image: %s", e)
        return None


def _maybe_compress(data: bytes) -> bytes:
    if len(data) <= _SIZE_BUDGET_BYTES:
        return data

    img = _safe_open(data)
    if img is None:
        # We couldn't safely decode it — pass through the original rather
        # than risking an OOM during resize. A 2-10 MB original is fine.
        return data

    # Preserve EXIF + ICC for orientation / colour fidelity.
    exif = img.info.get("exif")
    icc = img.info.get("icc_profile")

    img.thumbnail((_MAX_DIM, _MAX_DIM), Image.LANCZOS)

    out = BytesIO()
    fmt = (img.format or "PNG").upper()
    save_kwargs: dict = {"optimize": True}
    if exif:
        save_kwargs["exif"] = exif
    if icc:
        save_kwargs["icc_profile"] = icc

    if fmt in ("JPEG", "JPG"):
        img.convert("RGB").save(out, format="JPEG", quality=85, **save_kwargs)
    elif fmt == "PNG":
        img.save(out, format="PNG", **save_kwargs)
    else:
        # Convert exotic formats (TIFF, BMP, WEBP) to PNG for pdflatex.
        img.convert("RGBA").save(out, format="PNG", **save_kwargs)
    return out.getvalue()


def process_images(nodes: List[ImageNode]) -> Dict[str, bytes]:
    """Compress in-place and return a {filename: bytes} dict for packaging."""
    out: Dict[str, bytes] = {}
    for node in nodes:
        original_len = len(node.image_data)
        compressed = _maybe_compress(node.image_data)
        node.image_data = compressed
        if original_len > _SIZE_BUDGET_BYTES and not node.filename.lower().endswith(
            (".png", ".jpg", ".jpeg")
        ):
            node.filename = node.filename.rsplit(".", 1)[0] + ".png"
        out[node.filename] = compressed
    return out
