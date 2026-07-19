import base64
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field, model_validator
from pydantic_ai import Agent

_FORM_EXTRACTION_PROMPT = """You are a geometric document extraction engine.

Return reconstruction-grade data only. Do not summarize, normalize, correct, infer,
redesign, or omit empty objects. The coordinate origin is the page's top-left and
all coordinates are absolute pixels. Preserve exact text, whitespace, line breaks,
reading order, z-order, typography, colors, borders, tables, merged and empty cells,
form controls and their states, handwriting, signatures, stamps, images, logos,
watermarks, barcodes, QR codes, lines, shapes, and decorative objects.

Every element must have a stable id, type, x, y, width, height, page_number, z_order,
and confidence. Lines must additionally include x1, y1, x2, y2, and stroke_width.
Tables must include every cell and every visible grid line. Never flatten a table.
Unknown visual properties must remain null or empty; never invent them.
"""

PIXELS_PER_POINT = 96.0 / 72.0
EMU_PER_PIXEL = 9525.0


class Geometry(BaseModel):
    x: float
    y: float
    width: float
    height: float

    @model_validator(mode="after")
    def validate_geometry(self) -> "Geometry":
        if min(self.x, self.y, self.width, self.height) < 0:
            self.x = max(0.0, self.x)
            self.y = max(0.0, self.y)
            self.width = max(0.0, self.width)
            self.height = max(0.0, self.height)
        return self


class LineGeometry(Geometry):
    x1: float
    y1: float
    x2: float
    y2: float
    stroke_width: float = 1.0


class ReconstructionElement(Geometry):
    id: str
    type: str
    page_number: int = 1
    z_order: int = 0
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    parent_id: Optional[str] = None
    reading_order: Optional[int] = None
    rotation: float = 0.0
    text: Optional[str] = None
    font_family: Optional[str] = None
    font_size: Optional[float] = None
    font_weight: Optional[str] = None
    font_style: Optional[str] = None
    alignment: Optional[str] = None
    line_height: Optional[float] = None
    letter_spacing: Optional[float] = None
    opacity: Optional[float] = None
    text_color: Optional[str] = None
    background_color: Optional[str] = None
    fill_color: Optional[str] = None
    border_color: Optional[str] = None
    border_style: Optional[str] = None
    border_thickness: Optional[float] = None
    stroke_color: Optional[str] = None
    checked: Optional[bool] = None
    selected: Optional[bool] = None
    filled: Optional[bool] = None
    x1: Optional[float] = None
    y1: Optional[float] = None
    x2: Optional[float] = None
    y2: Optional[float] = None
    stroke_width: Optional[float] = None
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    row_heights: List[float] = Field(default_factory=list)
    column_widths: List[float] = Field(default_factory=list)
    cells: List[Dict[str, Any]] = Field(default_factory=list)
    grid_lines: List[Dict[str, Any]] = Field(default_factory=list)
    image_hash: Optional[str] = None
    image_type: Optional[str] = None
    image_data: Optional[str] = None
    visual_description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Rich extraction properties
    parent: Optional[str] = None
    children: List[str] = Field(default_factory=list)
    layer: Optional[str] = None
    group_id: Optional[str] = None
    border_radius: Optional[float] = None
    shadow: Optional[Dict[str, Any]] = None
    gradient: Optional[Dict[str, Any]] = None
    line_spacing: Optional[float] = None
    paragraph_spacing: Optional[float] = None
    anchor_point: Optional[str] = None
    underline: bool = False
    percentage_coordinates: Optional[Dict[str, float]] = None
    canvas_size: Optional[Dict[str, float]] = None
    stacking_order: Optional[int] = None
    bullet_character: Optional[str] = None
    indentation: Optional[float] = None
    level: Optional[int] = None
    number: Optional[str] = None
    caption: Optional[str] = None
    role: Optional[str] = None
    crop: Optional[Dict[str, float]] = None
    mask: Optional[str] = None


class PageMargins(BaseModel):
    top: Optional[float] = None
    right: Optional[float] = None
    bottom: Optional[float] = None
    left: Optional[float] = None


class ReconstructionDocument(BaseModel):
    page_width: float
    page_height: float
    units: Literal["pixels"] = "pixels"
    coordinate_system: Literal["top-left-origin"] = "top-left-origin"
    page_number: int = 1
    page_orientation: Optional[str] = None
    page_margins: Optional[PageMargins] = None
    scan_rotation: float = 0.0
    dpi: float = 300.0
    background_color: Optional[str] = None
    reading_order: List[str] = Field(default_factory=list)
    elements: List[ReconstructionElement] = Field(default_factory=list)

    # Grouped fields for rendering and lossless geometry reconstruction
    lines: List[Dict[str, Any]] = Field(default_factory=list)
    rectangles: List[Dict[str, Any]] = Field(default_factory=list)
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    checkboxes: List[Dict[str, Any]] = Field(default_factory=list)
    radio_buttons: List[Dict[str, Any]] = Field(default_factory=list)
    signature_fields: List[Dict[str, Any]] = Field(default_factory=list)
    images: List[Dict[str, Any]] = Field(default_factory=list)
    text_blocks: List[Dict[str, Any]] = Field(default_factory=list)

    # Page Integrity Validation Metadata
    document_id: Optional[str] = None
    image_hash: Optional[str] = None
    processing_timestamp: Optional[str] = None
    pipeline_version: Optional[str] = None


class FormExtractionResult(BaseModel):
    document: ReconstructionDocument


def correct_ocr_numeric_substitutions(text: str) -> str:
    """
    Corrects common OCR substitutions in numeric strings (e.g. 'O'/'Q' -> '0', 'I' -> '1', 'S' -> '5', 'B' -> '8')
    while preserving currency symbols, commas, decimals, leading/trailing zeros, and percentages.
    """
    if not text:
        return text
    
    trimmed = text.strip()
    if not trimmed:
        return text

    # Count numeric-like characters vs letters
    letters = 0
    digits_and_symbols = 0
    substitutions_found = 0
    
    # Numeric symbols
    symbols_set = set("$,€,£,¥,%,.,,,+,-,/,*, ")
    
    # Potential substitutions
    sub_map = {
        'O': '0', 'o': '0',
        'I': '1', 'i': '1', 'l': '1',
        'S': '5', 's': '5',
        'B': '8',
        'Q': '0', 'q': '0'
    }

    for char in trimmed:
        if char.isdigit() or char in symbols_set:
            digits_and_symbols += 1
        elif char in sub_map:
            substitutions_found += 1
        else:
            letters += 1

    if (digits_and_symbols + substitutions_found) > letters and (digits_and_symbols > 0 or substitutions_found > 0):
        corrected_chars = []
        for idx, char in enumerate(trimmed):
            if char in sub_map:
                is_numeric_ctx = False
                if idx > 0 and (trimmed[idx - 1].isdigit() or trimmed[idx - 1] in ".,$%"):
                    is_numeric_ctx = True
                if idx < len(trimmed) - 1 and (trimmed[idx + 1].isdigit() or trimmed[idx + 1] in ".,$%"):
                    is_numeric_ctx = True
                if len(trimmed) <= 5 and all(c.isdigit() or c in sub_map or c in symbols_set for c in trimmed):
                    is_numeric_ctx = True

                if is_numeric_ctx:
                    corrected_chars.append(sub_map[char])
                else:
                    corrected_chars.append(char)
            else:
                corrected_chars.append(char)
        return "".join(corrected_chars)

    return text


_form_agent: Optional[Agent] = None


def _get_form_agent() -> Optional[Agent]:
    global _form_agent
    if _form_agent is None:
        try:
            import os
            if "OLLAMA_BASE_URL" not in os.environ:
                host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
                if not host.endswith("/v1"):
                    host = f"{host}/v1"
                os.environ["OLLAMA_BASE_URL"] = host
            _form_agent = Agent(
                model="ollama:llama3.2-vision",
                output_type=FormExtractionResult,
                system_prompt=_FORM_EXTRACTION_PROMPT,
            )
        except Exception as exc:
            print(f"[FormExtractionAgent] Could not configure Ollama agent: {exc}")
            return None
    return _form_agent


class FormExtractionAgent:
    """Extract page primitives into a reconstruction-grade pixel schema."""

    def __init__(self, presentation_metadata: Optional[Dict[str, Any]] = None):
        self.presentation_metadata = presentation_metadata or {}

    def run(self, slide_model: Any, raw_page: Any = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Form extraction must be 100% deterministic and lossless.
        # We bypass unreliable vision LLMs to prevent coordinate corruption and text errors.
        page_width, page_height, scale = self._page_geometry(slide_model, raw_page)
        fallback = self._build_deterministic_result(
            slide_model, page_width, page_height, scale, raw_page=raw_page
        )
        if metadata:
            fallback.document.document_id = metadata.get("document_id")
            fallback.document.image_hash = metadata.get("image_hash")
            fallback.document.processing_timestamp = metadata.get("processing_timestamp")
            fallback.document.pipeline_version = metadata.get("pipeline_version")
        return fallback.model_dump(mode="json", exclude_none=True)

    def _page_geometry(
        self, slide_model: Any, raw_page: Any
    ) -> Tuple[float, float, float]:
        rect = getattr(raw_page, "rect", None)
        if rect is not None and getattr(rect, "width", 0) and getattr(rect, "height", 0):
            return (
                round(float(rect.width) * PIXELS_PER_POINT, 3),
                round(float(rect.height) * PIXELS_PER_POINT, 3),
                PIXELS_PER_POINT,
            )

        width = self.presentation_metadata.get("slide_width")
        height = self.presentation_metadata.get("slide_height")
        if width and height:
            return (
                round(float(width) / EMU_PER_PIXEL, 3),
                round(float(height) / EMU_PER_PIXEL, 3),
                1.0 / EMU_PER_PIXEL,
            )

        positions = [
            element.position
            for element in getattr(slide_model, "elements", [])
            if getattr(element, "position", None) is not None
        ]
        width = max((float(p.x + p.width) for p in positions), default=1.0)
        height = max((float(p.y + p.height) for p in positions), default=1.0)
        return round(width, 3), round(height, 3), 1.0

    def _page_image(self, slide_model: Any, raw_page: Any) -> Optional[Tuple[bytes, str]]:
        encoded = getattr(slide_model, "image_base64", None)
        if encoded:
            mime_type = "image/png"
            if encoded.startswith("data:"):
                header, encoded = encoded.split(",", 1)
                mime_type = header.split(";", 1)[0].split(":", 1)[1]
            return base64.b64decode(encoded), mime_type

        for element in getattr(slide_model, "elements", []):
            if getattr(element, "element_type", "") != "image":
                continue
            image_bytes = self._element_image_bytes(element)
            if image_bytes:
                return image_bytes, "image/png"

        get_pixmap = getattr(raw_page, "get_pixmap", None)
        if callable(get_pixmap):
            pixmap = get_pixmap(matrix=self._fitz_matrix(), alpha=False)
            return pixmap.tobytes("png"), "image/png"
        return None

    @staticmethod
    def _fitz_matrix() -> Any:
        import fitz
        return fitz.Matrix(PIXELS_PER_POINT, PIXELS_PER_POINT)

    @staticmethod
    def _scaled_bbox(position: Any, scale: float) -> Dict[str, float]:
        if position is None:
            return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
        return {
            "x": round(max(0.0, float(position.x) * scale), 3),
            "y": round(max(0.0, float(position.y) * scale), 3),
            "width": round(max(0.0, float(position.width) * scale), 3),
            "height": round(max(0.0, float(position.height) * scale), 3),
        }

    def _build_deterministic_result(
        self,
        slide_model: Any,
        page_width: float,
        page_height: float,
        scale: float,
        raw_page: Any = None,
    ) -> FormExtractionResult:
        elements: List[ReconstructionElement] = []
        source_elements = sorted(
            getattr(slide_model, "elements", []),
            key=lambda item: (
                int(getattr(item, "metadata", {}).get("z_order", 0)),
                float(getattr(getattr(item, "position", None), "y", 0)),
                float(getattr(getattr(item, "position", None), "x", 0)),
            ),
        )

        page_number = int(getattr(slide_model, "slide_number", 1))
        
        # 1. Process elements from slide model
        for reading_index, source in enumerate(source_elements):
            element = self._source_element(
                source, scale, reading_index, page_number, page_width, page_height
            )
            elements.append(element)

        # 2. Extract vector elements if PDF raw page is available
        next_z = max((element.z_order for element in elements), default=0) + 1
        if raw_page:
            vector_lines = self._extract_vector_lines(
                raw_page, scale, page_number, next_z
            )
            existing_ids = {element.id for element in elements}
            for line in vector_lines:
                if line.id not in existing_ids:
                    elements.append(line)
                    existing_ids.add(line.id)

            # Checkbox extraction from vector paths
            vector_checkboxes = self._extract_vector_checkboxes(
                raw_page, scale, page_number, next_z + len(vector_lines)
            )
            for cb in vector_checkboxes:
                if cb.id not in existing_ids:
                    elements.append(cb)
                    existing_ids.add(cb.id)

        # 3. Detect and insert checkboxes and lines if image is available and no vector page
        image_tuple = self._page_image(slide_model, raw_page)
        if image_tuple and not raw_page:
            img_bytes = image_tuple[0]
            # Run image-based line extraction (skip for slide layouts to prevent gridline artifacts)
            is_slide_layout = (page_width / page_height) > 1.2
            cv_lines = []
            if not is_slide_layout:
                cv_lines = self._extract_lines_from_image_bytes(
                    img_bytes, page_number, next_z + 200
                )
            existing_ids = {element.id for element in elements}
            for line in cv_lines:
                if line.id not in existing_ids:
                    elements.append(line)
                    existing_ids.add(line.id)

            # Run image-based checkbox extraction
            cv_checkboxes = self._extract_checkboxes_from_image_bytes(
                img_bytes, page_number, next_z + 400
            )
            for cb in cv_checkboxes:
                if cb.id not in existing_ids:
                    elements.append(cb)
                    existing_ids.add(cb.id)

        # 4. Check for text checkbox patterns like [ ] or [x] and update type
        for elem in elements:
            if elem.type in {"text_box", "text"}:
                text_content = (elem.text or "").strip()
                if text_content in {"[ ]", "[]", "☐"}:
                    elem.type = "checkbox"
                    elem.checked = False
                elif text_content in {"[x]", "[X]", "☑", "☒"}:
                    elem.type = "checkbox"
                    elem.checked = True

        # 5. Extract signature fields based on text proximity & keywords
        signature_fields = self._detect_signatures_from_text(elements, page_number)
        existing_ids = {element.id for element in elements}
        for sig in signature_fields:
            if sig.id not in existing_ids:
                elements.append(sig)
                existing_ids.add(sig.id)

        # Populate canvas_size, percentage_coordinates, layer, and stacking_order for all elements
        for elem in elements:
            elem.canvas_size = {"width": page_width, "height": page_height}
            elem.percentage_coordinates = {
                "x": round(elem.x / page_width, 5) if page_width > 0 else 0.0,
                "y": round(elem.y / page_height, 5) if page_height > 0 else 0.0,
                "width": round(elem.width / page_width, 5) if page_width > 0 else 0.0,
                "height": round(elem.height / page_height, 5) if page_height > 0 else 0.0,
            }
            if not elem.layer:
                elem_name = elem.metadata.get("name", "") if elem.metadata else ""
                elem.layer = self._determine_layer(elem.type, elem.width, elem.height, page_width, page_height, elem_name)
            elem.stacking_order = elem.z_order

        # 6. Group elements into sub-arrays for form_reconstruction_payload
        lines = []
        rectangles = []
        tables = []
        checkboxes = []
        radio_buttons = []
        signature_list = []
        images = []
        text_blocks = []

        for elem in elements:
            payload = elem.model_dump(exclude_none=True)
            etype = elem.type.lower()
            if etype == "line":
                lines.append(payload)
            elif etype in {"rectangle", "shape"}:
                rectangles.append(payload)
            elif etype == "table":
                tables.append(payload)
            elif etype == "checkbox":
                checkboxes.append(payload)
            elif etype == "radio_button":
                radio_buttons.append(payload)
            elif etype == "signature":
                signature_list.append(payload)
            elif etype == "image":
                images.append(payload)
            elif etype in {"text_box", "text"}:
                text_blocks.append(payload)

        document = ReconstructionDocument(
            page_width=page_width,
            page_height=page_height,
            page_number=page_number,
            page_orientation=self._page_orientation(page_width, page_height),
            scan_rotation=self._scan_rotation(slide_model, raw_page),
            dpi=self._dpi_estimate(scale, raw_page) or 300.0,
            background_color=getattr(slide_model, "background_color", None),
            reading_order=[element.id for element in elements],
            elements=elements,
            lines=lines,
            rectangles=rectangles,
            tables=tables,
            checkboxes=checkboxes,
            radio_buttons=radio_buttons,
            signature_fields=signature_list,
            images=images,
            text_blocks=text_blocks,
        )
        return FormExtractionResult(document=document)

    def _determine_layer(self, element_type: str, w: float, h: float, pw: float, ph: float, name: str = "") -> str:
        etype = element_type.lower()
        if etype == "image":
            return "Images"
        if etype == "table":
            return "Tables"
        if etype in {"line", "connector"}:
            return "Lines"
        if etype in {"text_box", "text"}:
            return "Text"
        if "icon" in name.lower() or "graphic" in name.lower() or (etype == "shape" and w < 48 and h < 48):
            return "Icons"
        if etype in {"shape", "rectangle", "group"}:
            if pw > 0 and ph > 0:
                area_ratio = (w * h) / (pw * ph)
                if area_ratio > 0.8:
                    return "Background"
                if area_ratio > 0.25:
                    return "Large panels"
            return "Shapes"
        return "Shapes"

    def _source_element(
        self, source: Any, scale: float, reading_index: int, page_number: int, page_width: float = 0.0, page_height: float = 0.0
    ) -> ReconstructionElement:
        bbox = self._scaled_bbox(getattr(source, "position", None), scale)
        metadata = dict(getattr(source, "metadata", {}) or {})
        element_type = str(getattr(source, "element_type", "unknown"))
        style = getattr(source, "style", None)
        confidence = float(metadata.get("confidence", 1.0) or 1.0)
        
        # Helper to extract a field from source, metadata, or style
        def get_prop(field_name, default=None):
            val = getattr(source, field_name, None)
            if val is not None:
                return val
            if metadata and field_name in metadata:
                return metadata[field_name]
            if style:
                val = getattr(style, field_name, None)
                if val is not None:
                    return val
            return default

        common: Dict[str, Any] = {
            **bbox,
            "id": str(getattr(source, "element_id", f"element_{reading_index}")),
            "type": element_type,
            "page_number": int(metadata.get("page_number", page_number)),
            "z_order": int(metadata.get("z_order", reading_index)),
            "reading_order": reading_index,
            "rotation": float(metadata.get("rotation", 0) or 0),
            "confidence": confidence,
            "text": correct_ocr_numeric_substitutions(getattr(source, "text", None)) if getattr(source, "text", None) is not None else None,
            "font_family": getattr(style, "font_name", None),
            "font_size": self._scaled_optional(getattr(style, "font_size", None), scale),
            "font_weight": getattr(source, "font_weight", None) or getattr(style, "font_weight", None) or ("bold" if getattr(style, "bold", False) else "normal"),
            "font_style": getattr(style, "font_style", None) or ("italic" if getattr(style, "italic", False) else "normal"),
            "alignment": getattr(style, "alignment", None),
            "line_height": self._scaled_optional(getattr(style, "line_spacing", None), scale),
            "text_color": getattr(style, "text_color", None),
            "background_color": getattr(style, "background_color", None),
            "fill_color": getattr(style, "background_color", None),
            "border_color": getattr(style, "border_color", None),
            "metadata": self._json_safe(metadata),

            # Layout, visual hierarchy, group, list, and image properties
            "parent": get_prop("parent"),
            "children": getattr(source, "children", []) or metadata.get("children", []),
            "group_id": get_prop("group_id"),
            "layer": get_prop("layer"),
            "border_radius": get_prop("border_radius"),
            "shadow": get_prop("shadow"),
            "gradient": get_prop("gradient"),
            "line_spacing": get_prop("line_spacing"),
            "paragraph_spacing": get_prop("paragraph_spacing"),
            "anchor_point": get_prop("anchor_point"),
            "underline": bool(getattr(source, "underline", False) or (style and getattr(style, "underline", False))),
            "bullet_character": get_prop("bullet_character"),
            "indentation": get_prop("indentation"),
            "level": get_prop("level"),
            "number": get_prop("number"),
            "caption": get_prop("caption"),
            "role": get_prop("role"),
            "crop": get_prop("crop"),
            "mask": get_prop("mask"),
            "stacking_order": int(metadata.get("z_order", reading_index)),
        }

        # Background color fallback
        if not common.get("background_color") and metadata.get("background_color"):
            common["background_color"] = metadata.get("background_color")
        if not common.get("fill_color") and metadata.get("fill_color"):
            common["fill_color"] = metadata.get("fill_color")

        if element_type == "line":
            common.update(
                x1=bbox["x"],
                y1=bbox["y"],
                x2=round(bbox["x"] + bbox["width"], 3),
                y2=round(bbox["y"] + bbox["height"], 3),
                stroke_width=max(1.0, min(bbox["width"], bbox["height"])),
                stroke_color=metadata.get("stroke_color") or getattr(style, "border_color", None),
            )
        elif element_type == "shape":
            line_geometry = self._infer_line_from_bbox(bbox, metadata)
            if line_geometry:
                common["type"] = "line"
                common.update(line_geometry)
            else:
                common["fill_color"] = metadata.get("fill_color") or getattr(style, "background_color", None)
                common["border_color"] = metadata.get("stroke_color") or getattr(style, "border_color", None)
                common["border_thickness"] = metadata.get("stroke_width")
        elif element_type == "table":
            common.update(self._table_geometry(source, bbox, scale))
        elif element_type == "image":
            image_bytes = self._element_image_bytes(source)
            if image_bytes:
                common["image_hash"] = hashlib.sha256(image_bytes).hexdigest()
                common["image_data"] = base64.b64encode(image_bytes).decode("ascii")
                common["image_type"] = metadata.get("mime_type", "image/png")
            common["visual_description"] = metadata.get("description")
        elif element_type == "checkbox":
            checked = metadata.get("is_checked")
            if checked is None:
                checked = metadata.get("checked")
            common["checked"] = bool(checked) if checked is not None else None
            common["type"] = "checkbox"
        elif element_type == "radio_button":
            selected = metadata.get("is_selected")
            if selected is None:
                selected = metadata.get("selected")
            common["selected"] = bool(selected) if selected is not None else None
            common["type"] = "radio_button"
        elif element_type in {"text_field", "signature", "stamp", "seal"}:
            common["filled"] = bool(getattr(source, "text", None))

        return ReconstructionElement(**common)

    def _table_geometry(
        self, source: Any, bbox: Dict[str, float], scale: float
    ) -> Dict[str, Any]:
        raw_rows = list(getattr(source, "raw_table_content", None) or [])
        reconstruction = getattr(source, "table_reconstruction", None)
        reconstructed_cells = list(getattr(reconstruction, "cells", []) or [])
        merged_cells = self._collect_merged_cells(source, reconstruction)
        row_count = len(raw_rows)
        column_count = max((len(row) for row in raw_rows), default=0)
        if reconstructed_cells:
            row_count = max(
                int(cell.row) + int(getattr(cell, "row_span", 1))
                for cell in reconstructed_cells
            )
            column_count = max(
                int(cell.column) + int(getattr(cell, "column_span", 1))
                for cell in reconstructed_cells
            )
        row_count = max(row_count, 1)
        column_count = max(column_count, 1)

        rec_row_heights = getattr(reconstruction, "row_heights", None)
        rec_col_widths = getattr(reconstruction, "column_widths", None)
        
        if rec_row_heights and len(rec_row_heights) == row_count:
            row_heights = [round(h * scale, 3) for h in rec_row_heights]
        else:
            row_heights = [round(bbox["height"] / row_count, 3)] * row_count
            
        if rec_col_widths and len(rec_col_widths) == column_count:
            column_widths = [round(w * scale, 3) for w in rec_col_widths]
        else:
            column_widths = [round(bbox["width"] / column_count, 3)] * column_count
        covered = self._merged_cell_coverage(merged_cells)
        cells: List[Dict[str, Any]] = []

        if reconstructed_cells:
            for cell in reconstructed_cells:
                if (int(cell.row), int(cell.column)) in covered:
                    continue
                geometry = getattr(cell, "cell_geometry", {}) or {}
                if geometry:
                    cell_bbox = {
                        "x": round(float(geometry.get("x", 0)) * scale, 3),
                        "y": round(float(geometry.get("y", 0)) * scale, 3),
                        "width": round(float(geometry.get("width", 0)) * scale, 3),
                        "height": round(float(geometry.get("height", 0)) * scale, 3),
                    }
                else:
                    cell_bbox = self._merged_cell_bbox(
                        int(cell.row),
                        int(cell.column),
                        int(getattr(cell, "row_span", 1)),
                        int(getattr(cell, "column_span", 1)),
                        bbox,
                        row_heights,
                        column_widths,
                    )
                cells.append(self._cell_dict(cell, cell_bbox))
        else:
            for row_index in range(row_count):
                row = raw_rows[row_index] if row_index < len(raw_rows) else []
                for column_index in range(column_count):
                    if (row_index, column_index) in covered:
                        continue
                    rowspan, colspan = self._span_at(
                        merged_cells, row_index, column_index
                    )
                    cell_bbox = self._merged_cell_bbox(
                        row_index,
                        column_index,
                        rowspan,
                        colspan,
                        bbox,
                        row_heights,
                        column_widths,
                    )
                    style = self._table_cell_style(source, row_index, column_index)
                    cell_text = str(row[column_index]) if column_index < len(row) else ""
                    cell_payload = {
                        "id": f"{getattr(source, 'element_id', 'table')}_r{row_index}_c{column_index}",
                        "row": row_index,
                        "column": column_index,
                        "rowspan": rowspan,
                        "colspan": colspan,
                        **cell_bbox,
                        "text": correct_ocr_numeric_substitutions(cell_text),
                    }
                    if style:
                        cell_payload.update(self._cell_style_fields(style))
                    cells.append(cell_payload)

        grid_lines = self._grid_lines_from_cells(cells, bbox, row_count, column_count)
        return {
            "row_count": row_count,
            "column_count": column_count,
            "row_heights": row_heights,
            "column_widths": column_widths,
            "cells": cells,
            "grid_lines": grid_lines,
        }

    @staticmethod
    def _collect_merged_cells(source: Any, reconstruction: Any) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        table_structure = getattr(source, "table_structure", None)
        buckets = [
            getattr(source, "table_merged_cells", None),
            table_structure.get("merged_cells")
            if isinstance(table_structure, dict)
            else None,
            getattr(reconstruction, "merged_cells", None) if reconstruction else None,
            getattr(
                getattr(reconstruction, "table_render_model", None),
                "merged_regions",
                None,
            )
            if reconstruction
            else None,
        ]
        for bucket in buckets:
            if not bucket:
                continue
            for item in bucket:
                if not isinstance(item, dict):
                    continue
                merged.append(
                    {
                        "row": int(item.get("row", item.get("row_index", 0))),
                        "column": int(item.get("column", item.get("column_index", 0))),
                        "row_span": int(item.get("row_span", item.get("rowspan", 1))),
                        "column_span": int(
                            item.get("column_span", item.get("colspan", 1))
                        ),
                    }
                )
        unique: List[Dict[str, Any]] = []
        seen = set()
        for item in merged:
            key = (item["row"], item["column"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    @staticmethod
    def _merged_cell_coverage(merged_cells: List[Dict[str, Any]]) -> set[Tuple[int, int]]:
        covered: set[Tuple[int, int]] = set()
        for merge in merged_cells:
            origin = (merge["row"], merge["column"])
            for row in range(merge["row"], merge["row"] + merge["row_span"]):
                for column in range(
                    merge["column"], merge["column"] + merge["column_span"]
                ):
                    if (row, column) != origin:
                        covered.add((row, column))
        return covered

    @staticmethod
    def _span_at(
        merged_cells: List[Dict[str, Any]], row: int, column: int
    ) -> Tuple[int, int]:
        for merge in merged_cells:
            if merge["row"] == row and merge["column"] == column:
                return merge["row_span"], merge["column_span"]
        return 1, 1

    @staticmethod
    def _merged_cell_bbox(
        row: int,
        column: int,
        rowspan: int,
        colspan: int,
        table_bbox: Dict[str, float],
        row_heights: List[float],
        column_widths: List[float],
    ) -> Dict[str, float]:
        x = round(table_bbox["x"] + sum(column_widths[:column]), 3)
        y = round(table_bbox["y"] + sum(row_heights[:row]), 3)
        width = round(sum(column_widths[column : column + colspan]), 3)
        height = round(sum(row_heights[row : row + rowspan]), 3)
        return {"x": x, "y": y, "width": width, "height": height}

    @staticmethod
    def _table_cell_style(source: Any, row_index: int, column_index: int) -> Any:
        styles = getattr(source, "raw_table_styles", None)
        if not styles or row_index >= len(styles):
            return None
        row_styles = styles[row_index]
        if column_index >= len(row_styles):
            return None
        return row_styles[column_index]

    @staticmethod
    def _cell_style_fields(style: Any) -> Dict[str, Any]:
        return {
            "fill_color": getattr(style, "background_color", None),
            "border_color": getattr(style, "border_color", None),
            "font_size": getattr(style, "font_size", None),
            "font_family": getattr(style, "font_name", None),
            "font_weight": "bold" if getattr(style, "bold", False) else "normal",
            "font_style": "italic" if getattr(style, "italic", False) else "normal",
            "text_color": getattr(style, "text_color", None),
            "alignment": getattr(style, "alignment", None),
            "vertical_alignment": getattr(style, "vertical_alignment", None),
        }

    @staticmethod
    def _cell_dict(cell: Any, bbox: Dict[str, float]) -> Dict[str, Any]:
        payload = {
            "id": str(getattr(cell, "cell_id", "") or f"cell_{cell.row}_{cell.column}"),
            "row": int(cell.row),
            "column": int(cell.column),
            "rowspan": int(getattr(cell, "row_span", 1)),
            "colspan": int(getattr(cell, "column_span", 1)),
            **bbox,
            "text": correct_ocr_numeric_substitutions(str(getattr(cell, "text", ""))),
        }
        fill_color = getattr(cell, "background_color", None)
        if fill_color:
            payload["fill_color"] = fill_color
            
        font_size = getattr(cell, "font_size", None)
        if font_size:
            payload["font_size"] = font_size
            
        font_weight = getattr(cell, "font_weight", None)
        if font_weight:
            payload["font_weight"] = font_weight
            
        alignment = getattr(cell, "alignment", None)
        if alignment:
            payload["alignment"] = alignment
            
        v_alignment = getattr(cell, "vertical_alignment", None)
        if v_alignment:
            payload["vertical_alignment"] = v_alignment

        style = getattr(cell, "style", None)
        if style:
            payload.update(FormExtractionAgent._cell_style_fields(style))
            
        # Add custom borders if present on cell
        for b_name in ["border_top", "border_bottom", "border_left", "border_right"]:
            b_val = getattr(cell, b_name, None)
            if b_val:
                payload[b_name] = b_val.model_dump() if hasattr(b_val, "model_dump") else b_val
        return payload

    @staticmethod
    def _grid_lines_from_cells(
        cells: List[Dict[str, Any]],
        table_bbox: Dict[str, float],
        row_count: int,
        column_count: int,
    ) -> List[Dict[str, Any]]:
        has_explicit_borders = any(
            ("border_top" in cell or "border_bottom" in cell or "border_left" in cell or "border_right" in cell)
            for cell in cells
        )
        
        if has_explicit_borders:
            lines = []
            for cell in cells:
                cx = cell["x"]
                cy = cell["y"]
                cw = cell["width"]
                ch = cell["height"]
                
                # Check top border
                if cell.get("border_top"):
                    bt = cell["border_top"]
                    lines.append({
                        "type": "line",
                        "x1": cx,
                        "y1": cy,
                        "x2": cx + cw,
                        "y2": cy,
                        "stroke_width": bt.get("width", 1.0),
                        "stroke_color": bt.get("color", "#000000")
                    })
                # Check bottom border
                if cell.get("border_bottom"):
                    bb = cell["border_bottom"]
                    lines.append({
                        "type": "line",
                        "x1": cx,
                        "y1": cy + ch,
                        "x2": cx + cw,
                        "y2": cy + ch,
                        "stroke_width": bb.get("width", 1.0),
                        "stroke_color": bb.get("color", "#000000")
                    })
                # Check left border
                if cell.get("border_left"):
                    bl = cell["border_left"]
                    lines.append({
                        "type": "line",
                        "x1": cx,
                        "y1": cy,
                        "x2": cx,
                        "y2": cy + ch,
                        "stroke_width": bl.get("width", 1.0),
                        "stroke_color": bl.get("color", "#000000")
                    })
                # Check right border
                if cell.get("border_right"):
                    br = cell["border_right"]
                    lines.append({
                        "type": "line",
                        "x1": cx + cw,
                        "y1": cy,
                        "x2": cx + cw,
                        "y2": cy + ch,
                        "stroke_width": br.get("width", 1.0),
                        "stroke_color": br.get("color", "#000000")
                    })
            return lines
            
        if cells:
            x_coords = sorted(
                {
                    round(cell["x"], 3)
                    for cell in cells
                }
                | {
                    round(cell["x"] + cell["width"], 3)
                    for cell in cells
                }
            )
            y_coords = sorted(
                {
                    round(cell["y"], 3)
                    for cell in cells
                }
                | {
                    round(cell["y"] + cell["height"], 3)
                    for cell in cells
                }
            )
        else:
            x_coords = [
                round(table_bbox["x"] + table_bbox["width"] * column / column_count, 3)
                for column in range(column_count + 1)
            ]
            y_coords = [
                round(table_bbox["y"] + table_bbox["height"] * row / row_count, 3)
                for row in range(row_count + 1)
            ]

        lines: List[Dict[str, Any]] = []
        left = round(table_bbox["x"], 3)
        right = round(table_bbox["x"] + table_bbox["width"], 3)
        top = round(table_bbox["y"], 3)
        bottom = round(table_bbox["y"] + table_bbox["height"], 3)
        for y in y_coords:
            lines.append(
                {
                    "type": "line",
                    "x1": left,
                    "y1": y,
                    "x2": right,
                    "y2": y,
                    "stroke_width": 1.0,
                }
            )
        for x in x_coords:
            lines.append(
                {
                    "type": "line",
                    "x1": x,
                    "y1": top,
                    "x2": x,
                    "y2": bottom,
                    "stroke_width": 1.0,
                }
            )
        return lines

    @staticmethod
    def _infer_line_from_bbox(
        bbox: Dict[str, float], metadata: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        width = bbox["width"]
        height = bbox["height"]
        if width <= 0 or height <= 0:
            return None
        stroke_color = metadata.get("stroke_color")
        if height <= max(3.0, width * 0.08):
            y = round(bbox["y"] + height / 2, 3)
            return {
                "x1": bbox["x"],
                "y1": y,
                "x2": round(bbox["x"] + width, 3),
                "y2": y,
                "stroke_width": max(1.0, height),
                "stroke_color": stroke_color,
            }
        if width <= max(3.0, height * 0.08):
            x = round(bbox["x"] + width / 2, 3)
            return {
                "x1": x,
                "y1": bbox["y"],
                "x2": x,
                "y2": round(bbox["y"] + height, 3),
                "stroke_width": max(1.0, width),
                "stroke_color": stroke_color,
            }
        return None

    def _extract_vector_lines(self, raw_page: Any, scale: float, page_number: int, start_z: int) -> List[ReconstructionElement]:
        get_drawings = getattr(raw_page, "get_drawings", None)
        if not callable(get_drawings):
            return []

        lines: List[ReconstructionElement] = []
        try:
            for drawing_index, drawing in enumerate(get_drawings()):
                stroke = drawing.get("color") or drawing.get("stroke")
                stroke_color = self._fitz_color_hex(stroke)
                stroke_width = float(drawing.get("width") or 1.0)
                for segment_index, item in enumerate(drawing.get("items", [])):
                    if not item or item[0] != "l":
                        continue
                    p1, p2 = item[1], item[2]
                    x1 = round(float(p1.x) * scale, 3)
                    y1 = round(float(p1.y) * scale, 3)
                    x2 = round(float(p2.x) * scale, 3)
                    y2 = round(float(p2.y) * scale, 3)
                    left = min(x1, x2)
                    top = min(y1, y2)
                    width = max(abs(x2 - x1), stroke_width)
                    height = max(abs(y2 - y1), stroke_width)
                    lines.append(
                        ReconstructionElement(
                            id=f"vector_line_{page_number}_{drawing_index}_{segment_index}",
                            type="line",
                            x=left,
                            y=top,
                            width=width,
                            height=height,
                            page_number=page_number,
                            z_order=start_z + len(lines),
                            reading_order=None,
                            x1=x1,
                            y1=y1,
                            x2=x2,
                            y2=y2,
                            stroke_width=max(1.0, stroke_width * scale),
                            stroke_color=stroke_color,
                            confidence=1.0,
                        )
                    )
        except Exception:
            return lines
        return lines

    def _extract_vector_checkboxes(self, raw_page: Any, scale: float, page_number: int, start_z: int) -> List[ReconstructionElement]:
        get_drawings = getattr(raw_page, "get_drawings", None)
        if not callable(get_drawings):
            return []

        checkboxes: List[ReconstructionElement] = []
        try:
            for idx, drawing in enumerate(get_drawings()):
                rect = drawing.get("rect")
                if not rect:
                    continue
                rx0, ry0, rx1, ry1 = rect
                w = (rx1 - rx0) * scale
                h = (ry1 - ry0) * scale
                aspect_ratio = w / h if h > 0 else 0

                # Checkbox outline (small square)
                if 6 <= w <= 25 and 6 <= h <= 25 and 0.8 <= aspect_ratio <= 1.25:
                    checked = False
                    for d2 in get_drawings():
                        if d2 == drawing:
                            continue
                        rect2 = d2.get("rect")
                        if rect2:
                            ix0 = max(rx0, rect2[0])
                            iy0 = max(ry0, rect2[1])
                            ix1 = min(rx1, rect2[2])
                            iy1 = min(ry1, rect2[3])
                            if ix1 > ix0 and iy1 > iy0:
                                checked = True
                                break

                    checkboxes.append(
                        ReconstructionElement(
                            id=f"vector_cb_{page_number}_{idx}",
                            type="checkbox",
                            x=rx0 * scale,
                            y=ry0 * scale,
                            width=w,
                            height=h,
                            page_number=page_number,
                            z_order=start_z + len(checkboxes),
                            confidence=1.0,
                            checked=checked,
                            stroke_color=self._fitz_color_hex(drawing.get("color")),
                            stroke_width=1.0,
                        )
                    )
        except Exception:
            return checkboxes
        return checkboxes

    def _extract_lines_from_image_bytes(self, img_bytes: bytes, page_number: int, start_z: int) -> List[ReconstructionElement]:
        try:
            import cv2
            import numpy as np
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            if img is None:
                return []

            thresh = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
            lines = []

            # Horizontal lines
            h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
            detect_h = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)
            cnts_h = cv2.findContours(detect_h, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cnts_h = cnts_h[0] if len(cnts_h) == 2 else cnts_h[1]
            for idx, c in enumerate(cnts_h):
                x, y, w, h = cv2.boundingRect(c)
                if w > 20 and h <= 15:
                    lines.append(
                        ReconstructionElement(
                            id=f"cv_line_h_{page_number}_{idx}",
                            type="line",
                            x=float(x),
                            y=float(y),
                            width=float(w),
                            height=float(h),
                            page_number=page_number,
                            z_order=start_z + len(lines),
                            x1=float(x),
                            y1=float(y + h/2.0),
                            x2=float(x + w),
                            y2=float(y + h/2.0),
                            stroke_width=float(max(1.0, h)),
                            stroke_color="#000000",
                        )
                    )

            # Vertical lines
            v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
            detect_v = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=2)
            cnts_v = cv2.findContours(detect_v, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cnts_v = cnts_v[0] if len(cnts_v) == 2 else cnts_v[1]
            for idx, c in enumerate(cnts_v):
                x, y, w, h = cv2.boundingRect(c)
                if h > 20 and w <= 15:
                    lines.append(
                        ReconstructionElement(
                            id=f"cv_line_v_{page_number}_{idx}",
                            type="line",
                            x=float(x),
                            y=float(y),
                            width=float(w),
                            height=float(h),
                            page_number=page_number,
                            z_order=start_z + len(lines),
                            x1=float(x + w/2.0),
                            y1=float(y),
                            x2=float(x + w/2.0),
                            y2=float(y + h),
                            stroke_width=float(max(1.0, w)),
                            stroke_color="#000000",
                        )
                    )
            return lines
        except Exception:
            return []

    def _extract_checkboxes_from_image_bytes(self, img_bytes: bytes, page_number: int, start_z: int) -> List[ReconstructionElement]:
        try:
            import cv2
            import numpy as np
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            if img is None:
                return []

            thresh = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
            cnts = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            cnts = cnts[0] if len(cnts) == 2 else cnts[1]

            checkboxes = []
            for idx, c in enumerate(cnts):
                x, y, w, h = cv2.boundingRect(c)
                aspect_ratio = float(w) / h if h > 0 else 0
                if 8 <= w <= 32 and 8 <= h <= 32 and 0.8 <= aspect_ratio <= 1.25:
                    crop = thresh[y+2:y+h-2, x+2:x+w-2]
                    checked = False
                    if crop.size > 0:
                        black_percent = (np.sum(crop == 255) / crop.size) * 100
                        checked = black_percent > 15.0

                    checkboxes.append(
                        ReconstructionElement(
                            id=f"cv_cb_{page_number}_{idx}",
                            type="checkbox",
                            x=float(x),
                            y=float(y),
                            width=float(w),
                            height=float(h),
                            page_number=page_number,
                            z_order=start_z + len(checkboxes),
                            checked=checked,
                            stroke_width=1.0,
                        )
                    )

            # Filter overlapping/duplicates
            filtered = []
            for cb in checkboxes:
                is_dup = False
                for f in filtered:
                    overlap_x = max(0.0, min(cb.x + cb.width, f.x + f.width) - max(cb.x, f.x))
                    overlap_y = max(0.0, min(cb.y + cb.height, f.y + f.height) - max(cb.y, f.y))
                    if (overlap_x * overlap_y) > 0.5 * (cb.width * cb.height):
                        is_dup = True
                        break
                if not is_dup:
                    filtered.append(cb)
            return filtered
        except Exception:
            return []

    def _detect_signatures_from_text(self, elements: List[ReconstructionElement], page_number: int) -> List[ReconstructionElement]:
        signatures = []
        sig_keywords = {"signature", "sign here", "initials", "authorized signature", "approval"}
        for elem in elements:
            if elem.type in {"text_box", "text"}:
                text = (elem.text or "").lower()
                if any(kw in text for kw in sig_keywords):
                    sig_id = f"sig_field_{page_number}_{elem.id}"
                    signatures.append(
                        ReconstructionElement(
                            id=sig_id,
                            type="signature",
                            x=elem.x,
                            y=max(0.0, elem.y - 30.0),
                            width=max(120.0, elem.width),
                            height=25.0,
                            page_number=page_number,
                            z_order=elem.z_order + 1,
                            confidence=0.9,
                            filled=False,
                        )
                    )
        return signatures

    @staticmethod
    def _fitz_color_hex(color: Any) -> Optional[str]:
        if not color:
            return None
        try:
            if isinstance(color, (list, tuple)) and len(color) >= 3:
                return "#{:02x}{:02x}{:02x}".format(
                    int(float(color[0]) * 255),
                    int(float(color[1]) * 255),
                    int(float(color[2]) * 255),
                )
        except (TypeError, ValueError):
            return None
        return None

    @staticmethod
    def _page_orientation(page_width: float, page_height: float) -> str:
        if abs(page_width - page_height) < 0.01:
            return "square"
        return "landscape" if page_width > page_height else "portrait"

    @staticmethod
    def _scan_rotation(slide_model: Any, raw_page: Any) -> float:
        metadata = getattr(slide_model, "metadata", None) or {}
        if isinstance(metadata, dict) and metadata.get("rotation") is not None:
            return float(metadata["rotation"])
        rotation = getattr(raw_page, "rotation", None)
        if rotation is not None:
            return float(rotation)
        return 0.0

    @staticmethod
    def _dpi_estimate(scale: float, raw_page: Any) -> Optional[float]:
        if scale and scale > 0:
            return round(72.0 * scale, 2)
        return None

    @staticmethod
    def _scaled_optional(value: Any, scale: float) -> Optional[float]:
        return round(float(value) * scale, 3) if value is not None else None

    @staticmethod
    def _element_image_bytes(source: Any) -> Optional[bytes]:
        metadata = getattr(source, "metadata", {}) or {}
        value = metadata.get("__image_bytes") or metadata.get("image_base64")
        if not value:
            return None
        if isinstance(value, bytes):
            return value
        if isinstance(value, str) and value.startswith("data:"):
            value = value.split(",", 1)[1]
        try:
            return base64.b64decode(value)
        except (ValueError, TypeError):
            return None

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_safe(item) for item in value]
        if hasattr(value, "model_dump"):
            return cls._json_safe(value.model_dump())
        return str(value)

    @staticmethod
    def _vision_prompt(fallback: FormExtractionResult) -> str:
        return (
            "Use the source image to add visible primitives missing from this deterministic "
            "inventory. Preserve every supplied element and coordinate exactly. Return only "
            "the required schema. Deterministic inventory:\n"
            + json.dumps(fallback.model_dump(mode="json", exclude_none=True), ensure_ascii=False)
        )

    @staticmethod
    def _merge_with_deterministic(
        extracted: FormExtractionResult, fallback: FormExtractionResult
    ) -> FormExtractionResult:
        additional = [
            element
            for element in extracted.document.elements
            if element.id not in {item.id for item in fallback.document.elements}
        ]
        extracted.document.page_width = fallback.document.page_width
        extracted.document.page_height = fallback.document.page_height
        extracted.document.page_number = fallback.document.page_number
        extracted.document.page_orientation = fallback.document.page_orientation
        extracted.document.scan_rotation = fallback.document.scan_rotation
        extracted.document.dpi = fallback.document.dpi
        extracted.document.background_color = fallback.document.background_color
        extracted.document.elements = fallback.document.elements + additional
        extracted.document.reading_order = [item.id for item in extracted.document.elements]
        
        extracted.document.lines = fallback.document.lines + [
            elem.model_dump(exclude_none=True) for elem in additional if elem.type == "line"
        ]
        extracted.document.rectangles = fallback.document.rectangles + [
            elem.model_dump(exclude_none=True) for elem in additional if elem.type in {"rectangle", "shape"}
        ]
        extracted.document.tables = fallback.document.tables + [
            elem.model_dump(exclude_none=True) for elem in additional if elem.type == "table"
        ]
        extracted.document.checkboxes = fallback.document.checkboxes + [
            elem.model_dump(exclude_none=True) for elem in additional if elem.type == "checkbox"
        ]
        extracted.document.radio_buttons = fallback.document.radio_buttons + [
            elem.model_dump(exclude_none=True) for elem in additional if elem.type == "radio_button"
        ]
        extracted.document.signature_fields = fallback.document.signature_fields + [
            elem.model_dump(exclude_none=True) for elem in additional if elem.type == "signature"
        ]
        extracted.document.images = fallback.document.images + [
            elem.model_dump(exclude_none=True) for elem in additional if elem.type == "image"
        ]
        extracted.document.text_blocks = fallback.document.text_blocks + [
            elem.model_dump(exclude_none=True) for elem in additional if elem.type in {"text_box", "text"}
        ]
        return extracted
