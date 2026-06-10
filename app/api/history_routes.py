"""User-scoped conversion history endpoints.

All routes require a valid bearer token. The token's `sub` claim
identifies the user; every query is filtered by ``user_id`` so a token
holder can only ever see their own conversions.
"""

from __future__ import annotations

import zipfile
from datetime import datetime
from io import BytesIO
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import current_user_required
from app.db import get_db
from app.models import Conversion, User

router = APIRouter(prefix="/history", tags=["history"])


# ── Schemas ─────────────────────────────────────────────────────────────


class ConversionSummary(BaseModel):
    id: str
    filename: str
    template: str
    has_images: bool
    citation_count: int
    warning_count: int
    compile_ok: bool
    created_at: datetime


class ConversionDetail(ConversionSummary):
    latex_source: str
    warnings: list[str]
    compile_error: Optional[str]
    compile_error_line: Optional[int]
    figure_filenames: list[str]


class HistoryPage(BaseModel):
    items: list[ConversionSummary]
    total: int
    limit: int
    offset: int


def _summary(c: Conversion) -> ConversionSummary:
    w = c.warnings or []
    return ConversionSummary(
        id=c.id,
        filename=c.filename,
        template=c.template,
        has_images=c.has_images,
        citation_count=c.citation_count,
        warning_count=len(w),
        compile_ok=c.compile_ok,
        created_at=c.created_at,
    )


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get("", response_model=HistoryPage)
def list_history(
    user: Annotated[User, Depends(current_user_required)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> HistoryPage:
    total = db.scalar(
        select(func.count(Conversion.id)).where(Conversion.user_id == user.id)
    ) or 0
    rows = list(
        db.scalars(
            select(Conversion)
            .where(Conversion.user_id == user.id)
            .order_by(desc(Conversion.created_at))
            .limit(limit)
            .offset(offset)
        )
    )
    return HistoryPage(
        items=[_summary(r) for r in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/{conversion_id}", response_model=ConversionDetail)
def get_history_item(
    conversion_id: str,
    user: Annotated[User, Depends(current_user_required)],
    db: Annotated[Session, Depends(get_db)],
) -> ConversionDetail:
    c = db.get(Conversion, conversion_id, options=[selectinload(Conversion.figures)])
    if c is None or c.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return ConversionDetail(
        **_summary(c).model_dump(),
        latex_source=c.latex_source,
        warnings=c.warnings or [],
        compile_error=c.compile_error,
        compile_error_line=c.compile_error_line,
        figure_filenames=[f.filename for f in c.figures],
    )


@router.get("/{conversion_id}/download")
def download_history_item(
    conversion_id: str,
    user: Annotated[User, Depends(current_user_required)],
    db: Annotated[Session, Depends(get_db)],
):
    """Re-download a stored conversion (zip if it has figures, else .tex)."""
    c = db.get(Conversion, conversion_id, options=[selectinload(Conversion.figures)])
    if c is None or c.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # Zip whenever there are extra files to ship: figures and/or the
    # extracted references.bib the stored .tex's \bibliography references.
    has_figures = bool(c.has_images and c.figures)
    if has_figures or c.bibtex:
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("output.tex", c.latex_source)
            if c.bibtex:
                zf.writestr("references.bib", c.bibtex)
            if has_figures:
                for fig in c.figures:
                    zf.writestr(f"figures/{fig.filename}", fig.data)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="output.zip"'},
        )

    return Response(
        content=c.latex_source,
        media_type="text/plain",
        headers={"Content-Disposition": 'attachment; filename="output.tex"'},
    )


@router.delete("/{conversion_id}", status_code=204)
def delete_history_item(
    conversion_id: str,
    user: Annotated[User, Depends(current_user_required)],
    db: Annotated[Session, Depends(get_db)],
):
    c = db.get(Conversion, conversion_id)
    if c is None or c.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    db.delete(c)
    db.commit()
    return Response(status_code=204)
