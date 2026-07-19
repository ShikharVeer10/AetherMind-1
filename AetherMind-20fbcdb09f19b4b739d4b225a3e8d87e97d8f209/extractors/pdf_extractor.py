from services.semantic_table_service import SemanticTableService
from services.flexible_table_detector import FlexibleTableDetector
from typing import List, Optional
from pathlib import Path
import fitz
from models.document_model import (
    DocumentModel,
    DocumentElementModel,
    SlideModel,
    PositionModel,
    StyleModel,
    ParagraphModel,
    RunModel,
)
from services.layout_structure_service import LayoutStructureService
from services.table_service import TableService

class PDFExtractor:
    def __init__(self, pdf_file_path: str):
        self.pdf_file_path = Path(pdf_file_path)
        self.doc = fitz.open(pdf_file_path)
        self.table_service = TableService()
        self.layout_service = LayoutStructureService()
        self.flexible_table_detector = FlexibleTableDetector()
        self.semantic_table_service = SemanticTableService()

    def extract_document(self, target_pages: Optional[List[int]] = None) -> DocumentModel:
        extracted_slides = []
        for page_index, page in enumerate(self.doc):
            page_number = page_index + 1
            if target_pages and page_number not in target_pages:
                continue
                
            extracted_slide = self.extract_page(
                page=page, page_number=page_number
            )
            extracted_slides.append(extracted_slide)

        return DocumentModel(
            document_name=self.pdf_file_path.name,
            document_type="pdf",
            total_slides=len(extracted_slides),
            slides=extracted_slides,
            presentation_metadata={
                "pdf_version": self.doc.metadata.get("format", "PDF"),
                "author": self.doc.metadata.get("author", ""),
                "title": self.doc.metadata.get("title", ""),
                "subject": self.doc.metadata.get("subject", ""),
                "created": self.doc.metadata.get("creationDate", ""),
                "modified": self.doc.metadata.get("modDate", ""),
            },
        )
    def extract_table_as_list(self, table):

        table_data = []

        extracted = table.extract()

        for row in extracted:
            cleaned_row = []
            for cell in row:
                cleaned_row.append(
                    str(cell).strip()
                    if cell is not None
                    else ""
                )
            table_data.append(cleaned_row)
        return table_data

    def extract_page(self, page, page_number: int) -> SlideModel:
        scale = 12700.0
        page_height_points = page.rect.height

        all_visual_elements = []
        detected_tables = []
        z_order = 1

        text_dict = page.get_text("dict")
        blocks = text_dict.get("blocks", [])
        print("\nPAGE:", page_number)
        
        try:
            tables = page.find_tables()
            print("TABLES FOUND:", len(tables.tables))
        except Exception as e:
            print("TABLE DETECTION ERROR:", e)
            tables = None
        
        slide_title = self._deduce_title(
            blocks,
            page_height_points
        )

        # 1. Extract text spans and images as distinct DocumentElementModels
        span_id_counter = 1
        image_id_counter = 1
        for block_idx, block in enumerate(blocks):
            if block.get("type") == 0: # Text Block
                lines = block.get("lines", [])
                for line in lines:
                    line_spans = line.get("spans", [])
                    for span in line_spans:
                        span_text = span.get("text", "").strip()
                        if not span_text:
                            continue

                        bx0, by0, bx1, by1 = span["bbox"]
                        font_name = span.get("font", "")
                        font_size = span.get("size")
                        flags = span.get("flags", 0)
                        is_bold = bool(flags & 16) or "bold" in font_name.lower()
                        is_italic = bool(flags & 2) or "italic" in font_name.lower() or "oblique" in font_name.lower()
                        color_int = span.get("color")

                        style = StyleModel(
                            font_size=font_size,
                            font_name=font_name,
                            bold=is_bold,
                            italic=is_italic,
                            text_color=self._get_color_hex(color_int),
                        )

                        element_id = f"slide_{page_number}_span_{span_id_counter}"
                        elem = DocumentElementModel(
                            element_id=element_id,
                            element_type="text_box",
                            text=span_text,
                            paragraphs=[ParagraphModel(
                                level=0,
                                text=span_text,
                                runs=[RunModel(
                                    text=span_text,
                                    bold=is_bold,
                                    italic=is_italic,
                                    font_size=font_size,
                                    font_name=font_name,
                                    font_color=self._get_color_hex(color_int)
                                )]
                            )],
                            position=PositionModel(
                                x=bx0 * scale,
                                y=by0 * scale,
                                width=(bx1 - bx0) * scale,
                                height=(by1 - by0) * scale,
                            ),
                            style=style,
                            shape_type="rect",
                            metadata={
                                "name": f"Span {span_id_counter}",
                                "visible": True,
                                "is_placeholder": False,
                                "z_order": z_order,
                            },
                        )
                        all_visual_elements.append(elem)
                        span_id_counter += 1
                        z_order += 1
            elif block.get("type") == 1: # Image Block
                ix0, iy0, ix1, iy1 = block["bbox"]
                try:
                    # Capture image bytes for classification/summarization
                    clip = (ix0, iy0, ix1, iy1)
                    pix = page.get_pixmap(clip=clip, matrix=fitz.Matrix(2, 2))
                    img_bytes = pix.tobytes("jpeg")
                    
                    element_id = f"slide_{page_number}_image_{image_id_counter}"
                    w_img = (ix1 - ix0) * scale
                    h_img = (iy1 - iy0) * scale
                    
                    # Deduce image role
                    role = "illustration"
                    if page.rect.width > 0 and page.rect.height > 0:
                        area_ratio = ((ix1 - ix0) * (iy1 - iy0)) / (page.rect.width * page.rect.height)
                        if area_ratio > 0.8:
                            role = "background"
                        elif w_img < 48 and h_img < 48:
                            role = "icon"

                    elem = DocumentElementModel(
                        element_id=element_id,
                        element_type="image",
                        text="",
                        paragraphs=[],
                        position=PositionModel(
                            x=ix0 * scale,
                            y=iy0 * scale,
                            width=w_img,
                            height=h_img,
                        ),
                        opacity=1.0,
                        caption="",
                        role=role,
                        crop={"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0},
                        mask="none",
                        metadata={
                            "name": f"Image {image_id_counter}",
                            "visible": True,
                            "is_placeholder": False,
                            "z_order": z_order,
                            "__image_bytes": img_bytes,
                        },
                    )
                    all_visual_elements.append(elem)
                    image_id_counter += 1
                    z_order += 1
                except Exception as e:
                    print(f"Warning: Failed to capture image block {image_id_counter}: {e}")

        # 1.5 Extract vector graphics (lines, rects) for structural grid detection
        try:
            drawings = page.get_drawings()
            drawing_counter = 1
            for d in drawings:
                rect = d.get("rect")
                if rect:
                    rx0, ry0, rx1, ry1 = rect
                    # Keep all shapes, including full page background panels (> 10 sq pt)
                    if (rx1 - rx0) * (ry1 - ry0) > 10:
                        fill_color = self._fitz_color_to_hex(d.get("fill"))
                        border_color = self._fitz_color_to_hex(d.get("color"))
                        border_width = float(d.get("width") or 1.0)
                        opacity = float(d.get("fill_opacity") or d.get("opacity") or d.get("stroke_opacity") or 1.0)
                        
                        shape_type = "rect"
                        items = d.get("items", [])
                        if items and items[0][0] == "c":
                            shape_type = "circle"
                        elif items and items[0][0] == "l":
                            shape_type = "line"

                        elem = DocumentElementModel(
                            element_id=f"slide_{page_number}_drawing_{drawing_counter}",
                            element_type="shape",
                            text="",
                            paragraphs=[],
                            position=PositionModel(
                                x=rx0 * scale,
                                y=ry0 * scale,
                                width=(rx1 - rx0) * scale,
                                height=(ry1 - ry0) * scale,
                            ),
                            shape_type=shape_type,
                            opacity=opacity,
                            border_radius=0.0,
                            metadata={
                                "name": f"Drawing {drawing_counter}",
                                "visible": True,
                                "is_placeholder": False,
                                "z_order": z_order,
                                "fill_color": fill_color,
                                "stroke_color": border_color,
                                "stroke_width": border_width,
                            },
                        )
                        elem.style = StyleModel(
                            background_color=fill_color,
                            border_color=border_color,
                            border_thickness=border_width,
                            opacity=opacity
                        )
                        all_visual_elements.append(elem)
                        drawing_counter += 1
                        z_order += 1
        except Exception as e:
            print(f"Warning: Failed to extract drawings for grid detection: {e}")

        # 2. Native Table Processing
        consumed_element_ids = set()
        final_elements = []

        if tables:
            for table_idx, table in enumerate(tables.tables):
                raw_table_content = self.extract_table_as_list(table)
                if not raw_table_content:
                    continue

                # Mark spans inside native table as consumed and extract cell styles
                t_bx0, t_by0, t_bx1, t_by1 = table.bbox
                t_bx0, t_by0, t_bx1, t_by1 = t_bx0 * scale, t_by0 * scale, t_bx1 * scale, t_by1 * scale        

                raw_table_styles = []
                for r_idx, row in enumerate(table.rows):
                    row_styles = []
                    for c_idx, cell_bbox in enumerate(row.cells):
                        if cell_bbox is None:
                            row_styles.append(None)
                            continue

                        # Find background color for this cell
                        bg_color = self._get_background_color_at(page, cell_bbox)

                        # Find dominant text style for this cell
                        cell_style = None
                        for elem in all_visual_elements:
                            ex = elem.position.x
                            ey = elem.position.y
                            # Check if span is inside cell
                            if (cell_bbox[0]*scale - 500 <= ex <= cell_bbox[2]*scale + 500) and \
                               (cell_bbox[1]*scale - 500 <= ey <= cell_bbox[3]*scale + 500):
                                consumed_element_ids.add(elem.element_id)
                                if not cell_style and elem.style:
                                    cell_style = elem.style.model_copy()

                        if cell_style:
                            cell_style.background_color = bg_color
                        else:
                            cell_style = StyleModel(background_color=bg_color)

                        row_styles.append(cell_style)
                pdf_row_heights = [float(r.bbox[3] - r.bbox[1]) * scale for r in table.rows] if hasattr(table, "rows") and table.rows else None
                pdf_column_widths = [float(c.bbox[2] - c.bbox[0]) * scale for c in table.cols] if hasattr(table, "cols") and table.cols else None

                table_reconstruction = self.table_service.build_reconstruction_payload(
                    table_id=f"slide_{page_number}_table_{table_idx}",
                    raw_table_content=raw_table_content,
                    table_structure=table_structure,
                    table_render_model=table_render_model,
                    table_semantics=table_semantic_interpretation,
                    is_visual=False,
                    table_geometry={
                        "x": t_bx0,
                        "y": t_by0,
                        "width": t_bx1 - t_bx0,
                        "height": t_by1 - t_by0
                    },
                    raw_table_styles=raw_table_styles,
                    row_heights=pdf_row_heights,
                    column_widths=pdf_column_widths
                )

                table_element = DocumentElementModel(
                    element_id=f"slide_{page_number}_table_{table_idx}",
                    element_type="table",
                    text=table_markdown,
                    paragraphs=[],
                    position=PositionModel(
                        x=t_bx0,
                        y=t_by0,
                        width=t_bx1 - t_bx0,
                        height=t_by1 - t_by0,
                    ),
                    table_markdown=table_markdown,
                    raw_table_content=raw_table_content,
                    table_structure=table_structure,
                    table_render_model=table_render_model,
                    table_semantic_interpretation=table_semantic_interpretation,
                    table_reconstruction=table_reconstruction,
                    metadata={"z_order": z_order}
                )
                final_elements.append(table_element)
                detected_tables.append({
                    "rows": len(raw_table_content),
                    "columns": max(len(r) for r in raw_table_content) if raw_table_content else 0,
                    "content": raw_table_content
                })
                z_order += 1

        # 3. Flexible table detection on remaining spans
        remaining_spans = [e for e in all_visual_elements if e.element_id not in consumed_element_ids]
        visual_tables = self.flexible_table_detector.detect_visual_tables(remaining_spans)

        for vt_idx, visual_table in enumerate(visual_tables):
            raw_table_content = visual_table.get("rows", [])
            raw_table_styles = visual_table.get("styles", [])
            if not raw_table_content:
                continue

            consumed_element_ids.update(visual_table.get("consumed_ids", []))

            table_markdown = self.table_service.to_markdown(raw_table_content)
            table_structure = self.table_service.analyze_structure(raw_table_content)
            table_structure["merged_cells"] = visual_table.get("merged_cells", [])

            table_semantic_interpretation = self.table_service.generate_semantic_context(raw_table_content)
            table_render_model = self.table_service.build_render_model(raw_table_content, table_structure)
            bbox = visual_table.get("bbox", {"x": 0, "y": 0, "width": 0, "height": 0})

            # 3.1 Extract Background Colors for Visual Table Cells
            if not raw_table_styles:
                raw_table_styles = [[None for _ in row] for row in raw_table_content]

            for r_idx, row in enumerate(raw_table_content):
                for c_idx, text in enumerate(row):
                    # Estimate cell bbox for background color query
                    # This is approximate based on elements in that cell
                    cell_color = self._get_background_color_at(page, (bbox["x"]/scale, bbox["y"]/scale, (bbox["x"]+bbox["width"])/scale, (bbox["y"]+bbox["height"])/scale))
                    if cell_color:
                        if not raw_table_styles[r_idx][c_idx]:
                            raw_table_styles[r_idx][c_idx] = StyleModel(background_color=cell_color)
                        else:
                            raw_table_styles[r_idx][c_idx].background_color = cell_color

            table_reconstruction = self.table_service.build_reconstruction_payload(
                table_id=f"slide_{page_number}_vtable_{vt_idx}",
                raw_table_content=raw_table_content,
                table_structure=table_structure,
                table_render_model=table_render_model,
                table_semantics=table_semantic_interpretation,
                is_visual=True,
                table_geometry=bbox,
                raw_table_styles=raw_table_styles,
                row_heights=visual_table.get("row_heights"),
                column_widths=visual_table.get("column_widths")
            )

            table_element = DocumentElementModel(
                element_id=f"slide_{page_number}_vtable_{vt_idx}",
                element_type="table",
                text=table_markdown,
                paragraphs=[],
                position=PositionModel(
                    x=bbox["x"],
                    y=bbox["y"],
                    width=bbox["width"],
                    height=bbox["height"]
                ),
                table_markdown=table_markdown,
                raw_table_content=raw_table_content,
                table_structure=table_structure,
                table_render_model=table_render_model,
                table_semantic_interpretation=table_semantic_interpretation,
                table_reconstruction=table_reconstruction,
                table_merged_cells=visual_table.get("merged_cells", []),
                metadata={"z_order": z_order}
            )
            final_elements.append(table_element)

            detected_tables.append({
                "table_type": visual_table.get("table_type", "visual_table"),
                "rows": len(visual_table.get("rows", [])),
                "content": visual_table.get("rows", [])
            })
            z_order += 1

        # 4. Final collection of non-consumed spans
        for elem in all_visual_elements:
            if elem.element_id not in consumed_element_ids:
                final_elements.append(elem)

        # 5. Detect Slide Background Color
        slide_bg_color = self._get_background_color_at(page, (0, 0, page.rect.width, page.rect.height)) or "#ffffff"

        return SlideModel(
            slide_number=page_number,
            title=slide_title,
            elements=final_elements,
            background_color=slide_bg_color,
            detected_tables=detected_tables,
        )




    def _deduce_title(self,blocks: List[dict],page_height: float) -> Optional[str]:
        candidates = []

        for block in blocks:

            if block.get("type") != 0:
                continue

            bbox = block.get("bbox", (0, 0, 0, 0))
            y0 = bbox[1]

        # Ignore bottom 25% of page
            if y0 > page_height * 0.75:
                continue

            block_max_font = 0.0
            block_text = ""

            for line in block.get("lines", []):

                for span in line.get("spans", []):

                    block_max_font = max(
                    block_max_font,
                    span.get("size", 0.0)
                    )

                    block_text += span.get(
                    "text",
                    ""
                    )

            block_text = block_text.strip()

            if not block_text:
                continue

            candidates.append(
                {
                    "text": block_text,
                    "max_font": block_max_font,
                    "y0": y0,
                    "x0": bbox[0],
                }
            )

        if not candidates:
            return None

        global_max_font = max(
        candidate["max_font"]
        for candidate in candidates
        )
        font_threshold = global_max_font * 0.7
        title_candidates = [
            candidate
            for candidate in candidates
            if candidate["max_font"] >= font_threshold
        ]
        title_candidates.sort(
            key=lambda candidate: (
                candidate["y0"],
                candidate["x0"],
            )
        )
        if title_candidates:
            return (
                title_candidates[0]["text"]
                .replace("\n", " ")
                .strip()
            )
        return None

    def _get_color_hex(self,color_int: Optional[int]) -> Optional[str]:
        if color_int is None:
            return None
        try:
            r = (color_int >> 16) & 255
            g = (color_int >> 8) & 255
            b = color_int & 255
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return None

    def _get_background_color_at(self, page, bbox) -> Optional[str]:
        try:
            drawings = page.get_drawings()
            candidate_colors = []
            for d in drawings:
                # Check for fill property and intersection
                if d.get("fill") and d.get("rect"):
                    d_rect = d["rect"]
                    # Calculate intersection
                    ix0 = max(bbox[0], d_rect[0])
                    iy0 = max(bbox[1], d_rect[1])
                    ix1 = min(bbox[2], d_rect[2])
                    iy1 = min(bbox[3], d_rect[3])

                    if ix1 > ix0 and iy1 > iy0:
                        # Significant intersection found
                        area = (ix1 - ix0) * (iy1 - iy0)
                        if area > 10: # Minimum 10 sq points
                            color = d["fill"]
                            # fitz colors are (r, g, b) floats 0-1
                            hex_color = "#{:02x}{:02x}{:02x}".format(
                                int(color[0]*255), int(color[1]*255), int(color[2]*255)
                            )
                            candidate_colors.append(hex_color)

            # Return topmost (last in list) non-white color
            for c in reversed(candidate_colors):
                if c.lower() != "#ffffff":
                    return c
        except Exception:
            pass
        return None

    def _fitz_color_to_hex(self, color) -> Optional[str]:
        if not color:
            return None
        try:
            if isinstance(color, (list, tuple)) and len(color) >= 3:
                return "#{:02x}{:02x}{:02x}".format(
                    int(color[0]*255), int(color[1]*255), int(color[2]*255)
                )
        except Exception:
            pass
        return None