from __future__ import annotations

# FROZEN after Week 1. Changes need full team sign-off.

from typing import List, Literal, Optional, Union
from enum import Enum
from pydantic import BaseModel, Field

class TextAlign(str, Enum):
    """Text alignment options."""
    LEFT = "LEFT"
    CENTER = "CENTER"
    RIGHT = "RIGHT"
    JUSTIFY = "JUSTIFY"

class RunNode(BaseModel):
    """A run of text with consistent formatting."""
    node_type: Literal['run'] = 'run'
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    code: bool = False

class HeadingNode(BaseModel):
    """A heading element with a specific level."""
    node_type: Literal['heading'] = 'heading'
    level: int = Field(ge=1, le=4)
    runs: List[RunNode]

class ParagraphNode(BaseModel):
    """A standard paragraph containing text runs."""
    node_type: Literal['paragraph'] = 'paragraph'
    runs: List[RunNode]
    alignment: TextAlign = TextAlign.LEFT

class ListItemNode(BaseModel):
    """A single item in a list, which may contain sub-items."""
    node_type: Literal['list_item'] = 'list_item'
    runs: List[RunNode]
    level: int = Field(default=0, ge=0)
    sub_items: List['ListItemNode'] = []

class ListNode(BaseModel):
    """A list (ordered or unordered) containing list items."""
    node_type: Literal['list'] = 'list'
    ordered: bool
    items: List[ListItemNode]

class TableCellNode(BaseModel):
    """A single cell within a table row."""
    node_type: Literal['table_cell'] = 'table_cell'
    runs: List[RunNode]
    col_span: int = 1
    row_span: int = 1
    alignment: TextAlign = TextAlign.LEFT

class TableRowNode(BaseModel):
    """A row within a table, containing multiple cells."""
    node_type: Literal['table_row'] = 'table_row'
    cells: List[TableCellNode]
    is_header: bool = False

class TableNode(BaseModel):
    """A table element containing rows."""
    node_type: Literal['table'] = 'table'
    rows: List[TableRowNode]
    col_alignments: List[TextAlign]
    caption: Optional[str] = None

class ImageNode(BaseModel):
    """An image embedded in the document."""
    node_type: Literal['image'] = 'image'
    filename: str
    image_data: bytes
    caption: Optional[str] = None
    width_hint: Optional[float] = None

ListItemNode.model_rebuild()

class EquationNode(BaseModel):
    """A mathematical equation, inline or display mode."""
    node_type: Literal['equation'] = 'equation'
    omml_xml: str
    latex_string: Optional[str] = None
    display: bool = False

class FootnoteNode(BaseModel):
    """A footnote containing text runs."""
    node_type: Literal['footnote'] = 'footnote'
    runs: List[RunNode]

class HyperlinkNode(BaseModel):
    """A hyperlink containing text runs."""
    node_type: Literal['hyperlink'] = 'hyperlink'
    url: str
    runs: List[RunNode]

class CitationNode(BaseModel):
    """A citation reference."""
    node_type: Literal['citation'] = 'citation'
    display_text: str
    raw_xml: str
    source_id: Optional[str] = None

class PageBreakNode(BaseModel):
    """An explicit page break."""
    node_type: Literal['page_break'] = 'page_break'

IRNode = Union[
    HeadingNode, ParagraphNode, ListNode, TableNode, ImageNode,
    EquationNode, FootnoteNode, HyperlinkNode, CitationNode, PageBreakNode
]

class IRDocument(BaseModel):
    """Parser produces this. Renderer consumes this."""
    title: Optional[str] = None
    nodes: List[IRNode]
    warnings: List[str] = []

class ConversionResult(BaseModel):
    """The final result of the conversion job."""
    job_id: str
    latex_source: str
    has_images: bool
    warnings: List[str]
    template: str
    compile_ok: bool
    compile_error: Optional[str] = None
    compile_error_line: Optional[int] = None
    overleaf_temp_url: Optional[str] = None
