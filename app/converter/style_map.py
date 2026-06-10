"""Configurable Word-style → IR-role mapping (v2 roadmap: style mapping config).

Out of the box CoreTex recognises Word's built-in styles ("Heading 1",
"List Bullet", monospace fonts, …). Real documents frequently use *custom*
named styles instead — a house "Chapter Title" style, a "Code" paragraph
style, a localised "Liste". This module lets a deployment teach the parser
those mappings without touching code, via a small JSON file:

    {
      "headings": { "Chapter Title": 1, "Section Head": 2 },
      "code":     [ "Code", "Source Code", "Listing" ],
      "lists":    { "My Bullets": "bullet", "My Numbers": "number" }
    }

Resolution order in the parser (matching is case-insensitive, whitespace-
trimmed):
  * Headings and list kinds: the style map is consulted FIRST, so a custom
    mapped name overrides the built-in "Heading N" / "List Bullet" detection.
  * Code: the style map is OR'd with the built-in monospace-font detection —
    a paragraph is code if EITHER says so.
An empty/absent map is fully inert, i.e. the exact pre-v2 behaviour.

The file is located via the ``CORETEX_STYLE_MAP`` env var, or ``app/style_map.json``
beside the package if present. Absent/invalid config → an empty map, i.e. the
exact pre-v2 behaviour.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "style_map.json"


class StyleMap:
    """Immutable lookup of custom style names to IR roles."""

    def __init__(
        self,
        headings: Optional[Dict[str, int]] = None,
        code: Optional[List[str]] = None,
        lists: Optional[Dict[str, str]] = None,
    ) -> None:
        self._headings = {self._norm(k): int(v) for k, v in (headings or {}).items()}
        self._code = {self._norm(c) for c in (code or [])}
        self._lists = {self._norm(k): str(v).lower() for k, v in (lists or {}).items()}

    @staticmethod
    def _norm(name: str) -> str:
        return (name or "").strip().lower()

    @property
    def is_empty(self) -> bool:
        return not (self._headings or self._code or self._lists)

    def heading_level(self, style_name: Optional[str]) -> Optional[int]:
        if not style_name:
            return None
        lvl = self._headings.get(self._norm(style_name))
        if lvl is None:
            return None
        return max(1, min(lvl, 4))

    def is_code(self, style_name: Optional[str]) -> bool:
        return bool(style_name) and self._norm(style_name) in self._code

    def list_kind(self, style_name: Optional[str]) -> Optional[str]:
        """Return 'bullet' / 'number' for a mapped list style, else None."""
        if not style_name:
            return None
        return self._lists.get(self._norm(style_name))


def load_style_map(path: Optional[str] = None) -> StyleMap:
    """Load the style map from ``CORETEX_STYLE_MAP`` / default path (or empty)."""
    candidate = path or os.getenv("CORETEX_STYLE_MAP") or str(_DEFAULT_PATH)
    p = Path(candidate)
    if not p.exists():
        return StyleMap()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not load style map from %s: %s; using defaults.", p, e)
        return StyleMap()
    sm = StyleMap(
        headings=data.get("headings"),
        code=data.get("code"),
        lists=data.get("lists"),
    )
    if not sm.is_empty:
        logger.info("Loaded custom style map from %s", p)
    return sm


# Process-wide singleton; cheap to build, read at import time like settings.
STYLE_MAP = load_style_map()
