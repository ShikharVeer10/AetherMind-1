import base64
import os
from io import BytesIO
from typing import Any, Dict, List, Optional
from PIL import Image, ImageDraw, ImageFont


class FormRenderer:
    """
    Deterministic renderer that recreates a form from a geometric JSON payload.
    Uses Pillow to render lines, rectangles, tables, checkboxes, images, and text.
    """

    def __init__(self, default_font_path: Optional[str] = None):
        self.default_font_path = default_font_path

    @staticmethod
    def _sanitize_payload(payload: Any) -> Any:
        """
        Recursively removes all image-based binary data, hashes, Base64 strings,
        and embedded image references from the reconstruction payload.
        """
        if isinstance(payload, dict):
            keys_to_remove = {
                "image_data",
                "image_hash",
                "image_base64",
                "image_type",
                "image_bytes",
                "__image_bytes",
                "embedded_images",
                "screenshots",
                "raster_images"
            }
            sanitized = {}
            for k, v in payload.items():
                if k in keys_to_remove:
                    continue
                if k == "metadata" and isinstance(v, dict):
                    v = {mk: mv for mk, mv in v.items() if mk not in keys_to_remove}
                sanitized[k] = FormRenderer._sanitize_payload(v)
            return sanitized
        elif isinstance(payload, list):
            return [FormRenderer._sanitize_payload(item) for item in payload]
        return payload

    def _validate_and_verify_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates the extraction payload and corrects any anomalies (duplicates, drift, style/color loss)
        before reconstruction to guarantee 100% rendering fidelity.
        """
        import copy
        sanitized = copy.deepcopy(payload)

        page_width = float(
            sanitized.get("page_width") 
            or sanitized.get("canvas", {}).get("width_pixels") 
            or 960
        )
        page_height = float(
            sanitized.get("page_height") 
            or sanitized.get("canvas", {}).get("height_pixels") 
            or 1088
        )

        if page_width <= 0 or page_height <= 0:
            raise ValueError(f"Reconstruction rejected: invalid page dimensions {page_width}x{page_height}")

        keys = ["lines", "rectangles", "tables", "checkboxes", "radio_buttons", "signatures", "images", "text_blocks", "elements", "objects", "stamps", "seals"]
        
        seen_texts = set()
        seen_geometries = set()

        for key in keys:
            if key not in sanitized or not isinstance(sanitized[key], list):
                continue
            
            cleaned_list = []
            for item in sanitized[key]:
                if not isinstance(item, dict):
                    cleaned_list.append(item)
                    continue

                # 1. Duplication checks
                text = item.get("text", "")
                x = float(item.get("x", 0))
                y = float(item.get("y", 0))
                w = float(item.get("width", 0))
                h = float(item.get("height", 0))

                # Allow lines to have zero width/height, but not other elements
                if item.get("type") != "line" and key != "lines" and (w < 0 or h < 0):
                    raise ValueError(f"Reconstruction rejected: element {item.get('id')} has negative dimensions {w}x{h}")

                # Reject if coordinate deviates significantly (e.g., out of page bounds by more than 100px or extremely negative)
                if x < -100 or y < -100 or x > page_width + 100 or y > page_height + 100:
                    raise ValueError(f"Reconstruction rejected: element {item.get('id') or text} coordinates ({x}, {y}) deviate significantly from page boundaries")

                geo_key = (round(x, 2), round(y, 2), round(w, 2), round(h, 2))
                geo_text_key = (text, geo_key)
                
                # Filter out exact duplicate text at the exact same location
                if text and geo_text_key in seen_geometries:
                    print(f"[FormRenderer Validation] Removed duplicate element: {text} at {geo_key}")
                    continue
                
                if text:
                    seen_texts.add(text)
                seen_geometries.add(geo_text_key)

                # 2. Coordinate drift / out-of-bounds correction (minor correction only)
                if x < 0:
                    item["x"] = 0.0
                if y < 0:
                    item["y"] = 0.0
                if x + w > page_width:
                    excess = (x + w) - page_width
                    if x >= excess:
                        item["x"] = float(x - excess)
                    else:
                        item["x"] = 0.0
                        item["width"] = page_width
                if y + h > page_height:
                    excess = (y + h) - page_height
                    if y >= excess:
                        item["y"] = float(y - excess)
                    else:
                        item["y"] = 0.0
                        item["height"] = page_height

                # 3. Styling checks
                if "text_color" not in item:
                    item["text_color"] = "#000000"
                if "font_family" not in item:
                    item["font_family"] = "Arial"
                if "font_size" not in item:
                    item["font_size"] = 11.0

                # Check table cells styling and alignments
                if item.get("type") == "table" or "cells" in item or key == "tables":
                    cells = item.get("cells") or []
                    for cell in cells:
                        if "alignment" not in cell:
                            cell["alignment"] = "left"
                        if "vertical_alignment" not in cell:
                            cell["vertical_alignment"] = "middle"
                        cx = float(cell.get("x", 0))
                        cy = float(cell.get("y", 0))
                        cw = float(cell.get("width", 0))
                        ch = float(cell.get("height", 0))
                        
                        # Reject if cell coordinates deviate significantly from the parent table's boundaries
                        if cx < x - 20 or cy < y - 20 or (cx + cw) > (x + w) + 20 or (cy + ch) > (y + h) + 20:
                            raise ValueError(f"Reconstruction rejected: table cell at ({cx}, {cy}) deviates significantly from parent table boundaries")
                        
                        if cx < x or cy < y or cx + cw > x + w or cy + ch > y + h:
                            cell["x"] = max(x, min(cx, x + w - cw))
                            cell["y"] = max(y, min(cy, y + h - ch))

                cleaned_list.append(item)
            sanitized[key] = cleaned_list

        return sanitized

    def render_to_image(self, payload: Dict[str, Any]) -> Image.Image:
        """
        Renders the geometric form payload into a PIL Image.
        """
        # Ensure pure geometry-based rendering by completely stripping image binary/data fields
        payload = self._sanitize_payload(payload)
        payload = self._validate_and_verify_payload(payload)

        page_width = int(
            payload.get("page_width") 
            or payload.get("canvas", {}).get("width_pixels") 
            or 960
        )
        page_height = int(
            payload.get("page_height") 
            or payload.get("canvas", {}).get("height_pixels") 
            or 1088
        )
        bg_color_raw = (
            payload.get("background_color") 
            or payload.get("theme", {}).get("background_color") 
            or "#ffffff"
        )
        
        # Normalize background color (fitz hex or standard color names/hex)
        bg_color = self._normalize_color(bg_color_raw, default="#ffffff")

        # 1. Background
        img = Image.new("RGB", (page_width, page_height), bg_color)
        draw = ImageDraw.Draw(img, "RGBA")

        # Unpack elements with deduplication
        seen_ids = set()
        
        def add_unique(lst, item):
            iid = item.get("id")
            if iid:
                if iid in seen_ids:
                    return
                seen_ids.add(iid)
            lst.append(item)

        lines = []
        rectangles = []
        tables = []
        checkboxes = []
        radio_buttons = []
        signatures = []
        images = []
        text_blocks = []
        stamps = []

        for item in payload.get("lines") or []: add_unique(lines, item)
        for item in payload.get("rectangles") or []: add_unique(rectangles, item)
        for item in payload.get("tables") or []: add_unique(tables, item)
        for item in payload.get("checkboxes") or []: add_unique(checkboxes, item)
        for item in payload.get("radio_buttons") or []: add_unique(radio_buttons, item)
        for item in payload.get("signatures") or []: add_unique(signatures, item)
        for item in payload.get("images") or []: add_unique(images, item)
        for item in payload.get("text_blocks") or []: add_unique(text_blocks, item)
        for item in payload.get("stamps") or []: add_unique(stamps, item)
        for item in payload.get("seals") or []: add_unique(stamps, item)

        elements_list = payload.get("elements") or payload.get("objects") or []
        for elem in elements_list:
            if not isinstance(elem, dict):
                continue
            
            # Handle new schema coordinate nesting
            if "bbox" in elem and isinstance(elem["bbox"], dict) and "pixel" in elem["bbox"]:
                pixel_bbox = elem["bbox"]["pixel"]
                elem["x"] = pixel_bbox.get("x", elem.get("x", 0))
                elem["y"] = pixel_bbox.get("y", elem.get("y", 0))
                elem["width"] = pixel_bbox.get("width", elem.get("width", 0))
                elem["height"] = pixel_bbox.get("height", elem.get("height", 0))

            # Handle new schema style nesting
            if "style" in elem and isinstance(elem["style"], dict):
                style_dict = elem["style"]
                if "fill_color" in style_dict and "fill_color" not in elem:
                    elem["fill_color"] = style_dict["fill_color"]
                if "background_color" in style_dict and "background_color" not in elem:
                    elem["background_color"] = style_dict["background_color"]
                if "text_color" in style_dict and "text_color" not in elem:
                    elem["text_color"] = style_dict["text_color"]
                if "border_color" in style_dict and "border_color" not in elem:
                    elem["border_color"] = style_dict["border_color"]
                if "border_thickness" in style_dict and "border_thickness" not in elem:
                    elem["border_thickness"] = style_dict["border_thickness"]
                if "border_thickness" in style_dict and "border_width" not in elem:
                    elem["border_width"] = style_dict["border_thickness"]

            etype = elem.get("type", "").lower()
            if etype == "line":
                add_unique(lines, elem)
            elif etype in {"rectangle", "shape"}:
                add_unique(rectangles, elem)
            elif etype == "table":
                add_unique(tables, elem)
            elif etype == "checkbox":
                add_unique(checkboxes, elem)
            elif etype == "radio_button":
                add_unique(radio_buttons, elem)
            elif etype == "signature":
                add_unique(signatures, elem)
            elif etype == "image":
                add_unique(images, elem)
            elif etype in {"text_box", "text"}:
                add_unique(text_blocks, elem)
            elif etype in {"stamp", "seal"}:
                add_unique(stamps, elem)

        # Deduplicate table cell text against text blocks to avoid double text drawing/overlaps
        sorted_tbs = sorted(text_blocks, key=lambda tb: (float(tb.get("y", 0)), float(tb.get("x", 0))))
        all_cells = []
        for table in tables:
            cells = table.get("cells") or []
            for cell in cells:
                if cell.get("text"):
                    all_cells.append((table, cell))
        all_cells.sort(key=lambda x: (x[1].get("row", 0), x[1].get("column", 0)))
        
        used_tb_indices = set()
        for table, cell in all_cells:
            ctext = cell.get("text", "")
            ctext_norm = "".join(ctext.lower().split())
            
            best_idx = None
            best_dist = float("inf")
            for idx, tb in enumerate(sorted_tbs):
                if idx in used_tb_indices:
                    continue
                tb_text = tb.get("text", "")
                tb_text_norm = "".join(tb_text.lower().split())
                if ctext_norm == tb_text_norm or ctext_norm in tb_text_norm or tb_text_norm in ctext_norm:
                    cx = float(cell.get("x", 0))
                    cy_val = float(cell.get("y", 0))
                    cw = float(cell.get("width", 0))
                    ch = float(cell.get("height", 0))
                    ccx = cx + cw / 2.0
                    ccy = cy_val + ch / 2.0
                    
                    tx = float(tb.get("x", 0))
                    ty_val = float(tb.get("y", 0))
                    tw = float(tb.get("width", 0))
                    th = float(tb.get("height", 0))
                    tcx = tx + tw / 2.0
                    tcy = ty_val + th / 2.0
                    
                    dist = ((ccx - tcx)**2 + (ccy - tcy)**2)**0.5
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = idx
            
            if best_idx is not None and best_dist < 400.0:
                used_tb_indices.add(best_idx)
                cell["text"] = ""

        # 2. Images
        for item in images:
            self._draw_image(img, item)

        # 3. Lines
        for item in lines:
            self._draw_line(draw, item)

        # 4. Grid lines
        for table in tables:
            cells = table.get("cells") or []
            has_explicit_borders = any(
                ("border_top" in cell or "border_bottom" in cell or "border_left" in cell or "border_right" in cell)
                for cell in cells
            )
            if not has_explicit_borders:
                grid_lines = table.get("grid_lines") or []
                for line in grid_lines:
                    lx1 = float(line.get("x1", line.get("x", 0)))
                    ly1 = float(line.get("y1", line.get("y", 0)))
                    lx2 = float(line.get("x2", lx1 + line.get("width", 0)))
                    ly2 = float(line.get("y2", ly1 + line.get("height", 0)))
                    stroke = line.get("stroke_color") or table.get("stroke_color") or "#000000"
                    stroke_w = float(line.get("stroke_width") or table.get("stroke_width") or 1.0)
                    draw.line([lx1, ly1, lx2, ly2], fill=self._normalize_color_rgba(stroke), width=int(stroke_w))

        # 5. Rectangles (Fills)
        # Rectangle fills & table cell fills
        for rect in rectangles:
            x = float(rect.get("x", 0))
            y = float(rect.get("y", 0))
            w = float(rect.get("width", 0))
            h = float(rect.get("height", 0))
            fill = rect.get("fill_color") or rect.get("background_color")
            if fill:
                fill_color = self._normalize_color_rgba(fill)
                draw.rectangle([x, y, x + w, y + h], fill=fill_color, outline=None)

        for table in tables:
            cells = table.get("cells") or []
            for cell in cells:
                cx = float(cell.get("x", 0))
                cy = float(cell.get("y", 0))
                cw = float(cell.get("width", 0))
                ch = float(cell.get("height", 0))
                fill = cell.get("fill_color") or cell.get("background_color")
                if fill:
                    draw.rectangle([cx, cy, cx + cw, cy + ch], fill=self._normalize_color_rgba(fill), outline=None)

        # 6. Borders
        # Custom cell borders & rectangle outline borders
        for table in tables:
            cells = table.get("cells") or []
            has_explicit_borders = any(
                ("border_top" in cell or "border_bottom" in cell or "border_left" in cell or "border_right" in cell)
                for cell in cells
            )
            if has_explicit_borders:
                grid_lines = table.get("grid_lines") or []
                for line in grid_lines:
                    lx1 = float(line.get("x1", line.get("x", 0)))
                    ly1 = float(line.get("y1", line.get("y", 0)))
                    lx2 = float(line.get("x2", lx1 + line.get("width", 0)))
                    ly2 = float(line.get("y2", ly1 + line.get("height", 0)))
                    stroke = line.get("stroke_color") or table.get("stroke_color") or "#000000"
                    stroke_w = float(line.get("stroke_width") or table.get("stroke_width") or 1.0)
                    draw.line([lx1, ly1, lx2, ly2], fill=self._normalize_color_rgba(stroke), width=int(stroke_w))

        for rect in rectangles:
            x = float(rect.get("x", 0))
            y = float(rect.get("y", 0))
            w = float(rect.get("width", 0))
            h = float(rect.get("height", 0))
            stroke = rect.get("stroke_color") or rect.get("border_color")
            stroke_w = float(rect.get("stroke_width") or rect.get("border_thickness") or 0.0)
            if stroke and stroke_w > 0:
                stroke_color = self._normalize_color_rgba(stroke)
                draw.rectangle([x, y, x + w, y + h], fill=None, outline=stroke_color, width=int(stroke_w))

        # 7. Text
        # Text blocks
        for item in text_blocks:
            self._draw_text(draw, item)

        # Table cell text (with word-wrap and shrink-to-fit)
        for table in tables:
            cells = table.get("cells") or []
            for cell in cells:
                ctext = cell.get("text", "")
                if ctext:
                    cx = float(cell.get("x", 0))
                    cy = float(cell.get("y", 0))
                    cw = float(cell.get("width", 0))
                    ch = float(cell.get("height", 0))
                    
                    cfont_size = float(cell.get("font_size") or table.get("font_size") or 10.0)
                    cfont_family = cell.get("font_family") or table.get("font_family") or "Arial"
                    ctext_color = self._normalize_color_rgba(cell.get("text_color") or "#000000")
                    cfont_weight = cell.get("font_weight") or table.get("font_weight") or "normal"
                    cfont_style = cell.get("font_style") or table.get("font_style") or "normal"

                    padding_x = 5
                    usable_w = max(1, cw - 2 * padding_x)

                    # Shrink-to-fit for table cell text
                    min_font = 6.0
                    while cfont_size >= min_font:
                        font = self._load_font(cfont_family, cfont_size, cfont_weight, cfont_style)
                        wrapped_lines = self._word_wrap(ctext, font, usable_w, draw)
                        line_height = cfont_size * 1.2
                        total_text_h = len(wrapped_lines) * line_height
                        if total_text_h <= ch:
                            break
                        cfont_size -= 0.5
                    else:
                        cfont_size = min_font
                        font = self._load_font(cfont_family, cfont_size, cfont_weight, cfont_style)
                        wrapped_lines = self._word_wrap(ctext, font, usable_w, draw)
                        line_height = cfont_size * 1.2
                        total_text_h = len(wrapped_lines) * line_height

                    start_y = cy
                    valign = (cell.get("vertical_alignment") or table.get("vertical_alignment") or "middle").lower()
                    if valign == "bottom" and ch > total_text_h:
                        start_y = cy + ch - total_text_h - 2
                    elif (valign == "center" or valign == "middle") and ch > total_text_h:
                        start_y = cy + (ch - total_text_h) / 2
                    elif valign == "top":
                        start_y = cy + 2

                    for idx, lt in enumerate(wrapped_lines):
                        if not lt:
                            continue
                        try:
                            left_box, top_box, right_box, bottom_box = draw.textbbox((0, 0), lt, font=font)
                            lt_w = right_box - left_box
                        except Exception:
                            lt_w = len(lt) * cfont_size * 0.6
                        
                        align = (cell.get("alignment") or table.get("alignment") or "left").lower()
                        if align == "right":
                            tx = cx + cw - lt_w - padding_x
                        elif align == "center":
                            tx = cx + (cw - lt_w) / 2
                        else:
                            tx = cx + padding_x
                            
                        line_y = start_y + idx * line_height
                        draw.text((tx, line_y), lt, fill=ctext_color, font=font)

        # 8. Checkboxes
        for cb in checkboxes:
            self._draw_checkbox(draw, cb)
        for rb in radio_buttons:
            self._draw_radio_button(draw, rb)

        # 9. Signatures
        for sig in signatures:
            self._draw_signature(draw, sig)

        # 10. Stamps
        for stamp in stamps:
            self._draw_stamp(draw, stamp)

        return img

    def render_to_pdf(self, payload: Dict[str, Any], output_path: str) -> None:
        """
        Renders the geometric form payload into a ReportLab PDF at output_path.
        """
        # Ensure pure geometry-based rendering by completely stripping image binary/data fields
        payload = self._sanitize_payload(payload)
        payload = self._validate_and_verify_payload(payload)

        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import HexColor

        page_width = float(
            payload.get("page_width") 
            or payload.get("canvas", {}).get("width_pixels") 
            or 960
        )
        page_height = float(
            payload.get("page_height") 
            or payload.get("canvas", {}).get("height_pixels") 
            or 1088
        )
        
        c = canvas.Canvas(output_path, pagesize=(page_width, page_height))
        
        # ReportLab coordinate origin is bottom-left, but form payload is top-left.
        # We define a helper to convert y coordinate
        def cy(y: float, h: float = 0.0) -> float:
            return page_height - y - h

        # 1. Background
        bg_color_raw = (
            payload.get("background_color") 
            or payload.get("theme", {}).get("background_color") 
            or "#ffffff"
        )
        bg_hex = self._normalize_color(bg_color_raw, default="#ffffff")
        c.setFillColor(HexColor(bg_hex))
        c.rect(0, 0, page_width, page_height, fill=1, stroke=0)

        # Unpack elements with deduplication
        seen_ids = set()
        
        def add_unique(lst, item):
            iid = item.get("id")
            if iid:
                if iid in seen_ids:
                    return
                seen_ids.add(iid)
            lst.append(item)

        lines = []
        rectangles = []
        tables = []
        checkboxes = []
        radio_buttons = []
        signatures = []
        images = []
        text_blocks = []
        stamps = []

        for item in payload.get("lines") or []: add_unique(lines, item)
        for item in payload.get("rectangles") or []: add_unique(rectangles, item)
        for item in payload.get("tables") or []: add_unique(tables, item)
        for item in payload.get("checkboxes") or []: add_unique(checkboxes, item)
        for item in payload.get("radio_buttons") or []: add_unique(radio_buttons, item)
        for item in payload.get("signatures") or []: add_unique(signatures, item)
        for item in payload.get("images") or []: add_unique(images, item)
        for item in payload.get("text_blocks") or []: add_unique(text_blocks, item)
        for item in payload.get("stamps") or []: add_unique(stamps, item)
        for item in payload.get("seals") or []: add_unique(stamps, item)

        elements_list = payload.get("elements") or payload.get("objects") or []
        for elem in elements_list:
            if not isinstance(elem, dict):
                continue

            # Handle new schema coordinate nesting
            if "bbox" in elem and isinstance(elem["bbox"], dict) and "pixel" in elem["bbox"]:
                pixel_bbox = elem["bbox"]["pixel"]
                elem["x"] = pixel_bbox.get("x", elem.get("x", 0))
                elem["y"] = pixel_bbox.get("y", elem.get("y", 0))
                elem["width"] = pixel_bbox.get("width", elem.get("width", 0))
                elem["height"] = pixel_bbox.get("height", elem.get("height", 0))

            # Handle new schema style nesting
            if "style" in elem and isinstance(elem["style"], dict):
                style_dict = elem["style"]
                if "fill_color" in style_dict and "fill_color" not in elem:
                    elem["fill_color"] = style_dict["fill_color"]
                if "background_color" in style_dict and "background_color" not in elem:
                    elem["background_color"] = style_dict["background_color"]
                if "text_color" in style_dict and "text_color" not in elem:
                    elem["text_color"] = style_dict["text_color"]
                if "border_color" in style_dict and "border_color" not in elem:
                    elem["border_color"] = style_dict["border_color"]
                if "border_thickness" in style_dict and "border_thickness" not in elem:
                    elem["border_thickness"] = style_dict["border_thickness"]
                if "border_thickness" in style_dict and "border_width" not in elem:
                    elem["border_width"] = style_dict["border_thickness"]

            etype = elem.get("type", "").lower()
            if etype == "line":
                add_unique(lines, elem)
            elif etype in {"rectangle", "shape"}:
                add_unique(rectangles, elem)
            elif etype == "table":
                add_unique(tables, elem)
            elif etype == "checkbox":
                add_unique(checkboxes, elem)
            elif etype == "radio_button":
                add_unique(radio_buttons, elem)
            elif etype == "signature":
                add_unique(signatures, elem)
            elif etype == "image":
                add_unique(images, elem)
            elif etype in {"text_box", "text"}:
                add_unique(text_blocks, elem)
            elif etype in {"stamp", "seal"}:
                add_unique(stamps, elem)

        # Deduplicate table cell text against text blocks to avoid double text drawing/overlaps
        sorted_tbs = sorted(text_blocks, key=lambda tb: (float(tb.get("y", 0)), float(tb.get("x", 0))))
        all_cells = []
        for table in tables:
            cells = table.get("cells") or []
            for cell in cells:
                if cell.get("text"):
                    all_cells.append((table, cell))
        all_cells.sort(key=lambda x: (x[1].get("row", 0), x[1].get("column", 0)))
        
        used_tb_indices = set()
        for table, cell in all_cells:
            ctext = cell.get("text", "")
            ctext_norm = "".join(ctext.lower().split())
            
            best_idx = None
            best_dist = float("inf")
            for idx, tb in enumerate(sorted_tbs):
                if idx in used_tb_indices:
                    continue
                tb_text = tb.get("text", "")
                tb_text_norm = "".join(tb_text.lower().split())
                if ctext_norm == tb_text_norm or ctext_norm in tb_text_norm or tb_text_norm in ctext_norm:
                    cx = float(cell.get("x", 0))
                    cy_val = float(cell.get("y", 0))
                    cw = float(cell.get("width", 0))
                    ch = float(cell.get("height", 0))
                    ccx = cx + cw / 2.0
                    ccy = cy_val + ch / 2.0
                    
                    tx = float(tb.get("x", 0))
                    ty_val = float(tb.get("y", 0))
                    tw = float(tb.get("width", 0))
                    th = float(tb.get("height", 0))
                    tcx = tx + tw / 2.0
                    tcy = ty_val + th / 2.0
                    
                    dist = ((ccx - tcx)**2 + (ccy - tcy)**2)**0.5
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = idx
            
            if best_idx is not None and best_dist < 400.0:
                used_tb_indices.add(best_idx)
                cell["text"] = ""

        # 2. Images
        for item in images:
            x, y, w, h = item.get("x", 0), item.get("y", 0), item.get("width", 100), item.get("height", 100)
            if x <= 5 and y <= 5 and w >= page_width - 10 and h >= page_height - 10:
                pass
            else:
                c.setFillColor(HexColor("#f0f0f0"))
                c.setStrokeColor(HexColor("#cccccc"))
                c.setLineWidth(1.0)
                c.rect(x, cy(y, h), w, h, fill=1, stroke=1)
                c.setStrokeColor(HexColor("#dddddd"))
                c.line(x, cy(y), x + w, cy(y + h))
                c.line(x, cy(y + h), x + w, cy(y))
                c.setFont("Helvetica-Oblique", 8)
                c.setFillColor(HexColor("#777777"))
                c.drawString(x + 5, cy(y, h) + 5, "[Image]")

        # 3. Lines
        for item in lines:
            x1, y1 = item.get("x1", item.get("x", 0)), item.get("y1", item.get("y", 0))
            x2, y2 = item.get("x2", x1 + item.get("width", 0)), item.get("y2", y1 + item.get("height", 0))
            stroke = item.get("stroke_color") or "#000000"
            stroke_w = item.get("stroke_width", 1.0)
            c.setStrokeColor(HexColor(self._normalize_color(stroke)))
            c.setLineWidth(float(stroke_w))
            c.line(x1, cy(y1), x2, cy(y2))

        # 4. Grid lines
        for table in tables:
            cells = table.get("cells") or []
            has_explicit_borders = any(
                ("border_top" in cell or "border_bottom" in cell or "border_left" in cell or "border_right" in cell)
                for cell in cells
            )
            if not has_explicit_borders:
                grid_lines = table.get("grid_lines") or []
                for line in grid_lines:
                    lx1, ly1 = float(line.get("x1", line.get("x", 0))), float(line.get("y1", line.get("y", 0)))
                    lx2, ly2 = float(line.get("x2", lx1 + line.get("width", 0))), float(line.get("y2", ly1 + line.get("height", 0)))
                    stroke = line.get("stroke_color") or table.get("stroke_color") or "#000000"
                    stroke_w = float(line.get("stroke_width") or 1.0)
                    c.setStrokeColor(HexColor(self._normalize_color(stroke)))
                    c.setLineWidth(stroke_w)
                    c.line(lx1, cy(ly1), lx2, cy(ly2))

        # 5. Borders
        for table in tables:
            cells = table.get("cells") or []
            has_explicit_borders = any(
                ("border_top" in cell or "border_bottom" in cell or "border_left" in cell or "border_right" in cell)
                for cell in cells
            )
            if has_explicit_borders:
                grid_lines = table.get("grid_lines") or []
                for line in grid_lines:
                    lx1, ly1 = float(line.get("x1", line.get("x", 0))), float(line.get("y1", line.get("y", 0)))
                    lx2, ly2 = float(line.get("x2", lx1 + line.get("width", 0))), float(line.get("y2", ly1 + line.get("height", 0)))
                    stroke = line.get("stroke_color") or table.get("stroke_color") or "#000000"
                    stroke_w = float(line.get("stroke_width") or 1.0)
                    c.setStrokeColor(HexColor(self._normalize_color(stroke)))
                    c.setLineWidth(stroke_w)
                    c.line(lx1, cy(ly1), lx2, cy(ly2))

        # 5. Rectangles (Fills)
        for rect in rectangles:
            x, y, w, h = rect.get("x", 0), rect.get("y", 0), rect.get("width", 100), rect.get("height", 100)
            fill = rect.get("fill_color") or rect.get("background_color")
            if fill:
                c.setFillColor(HexColor(self._normalize_color(fill)))
                c.rect(x, cy(y, h), w, h, fill=1, stroke=0)

        for table in tables:
            cells = table.get("cells") or []
            for cell in cells:
                cx, cy_pos = float(cell.get("x", 0)), float(cell.get("y", 0))
                cw, ch = float(cell.get("width", 0)), float(cell.get("height", 0))
                fill = cell.get("fill_color") or cell.get("background_color")
                if fill:
                    c.setFillColor(HexColor(self._normalize_color(fill)))
                    c.rect(cx, cy(cy_pos, ch), cw, ch, fill=1, stroke=0)

        # 6. Borders
        for rect in rectangles:
            x, y, w, h = rect.get("x", 0), rect.get("y", 0), rect.get("width", 100), rect.get("height", 100)
            stroke = rect.get("stroke_color") or rect.get("border_color")
            stroke_w = rect.get("stroke_width") or rect.get("border_thickness") or 0.0
            if stroke and stroke_w > 0:
                c.setStrokeColor(HexColor(self._normalize_color(stroke)))
                c.setLineWidth(float(stroke_w))
                c.rect(x, cy(y, h), w, h, fill=0, stroke=1)

        # 7. Text
        # Text blocks
        for item in text_blocks:
            x, y, w, h = item.get("x", 0), item.get("y", 0), item.get("width", 100), item.get("height", 30)
            text = item.get("text", "")
            if text:
                font_size = float(item.get("font_size") or 10.0)
                if ("font_size" not in item or item["font_size"] == 10.0) and h > 12.0:
                    font_size = max(8.0, min(72.0, h * 0.75))
                font_name = "Helvetica"
                if "bold" in str(item.get("font_weight", "")).lower():
                    font_name = "Helvetica-Bold"
                if "italic" in str(item.get("font_style", "")).lower():
                    font_name += "-Oblique" if "Bold" not in font_name else "Oblique"
                    if font_name == "Helvetica-BoldOblique":
                        font_name = "Helvetica-BoldOblique"
                
                c.setFont(font_name, font_size)
                c.setFillColor(HexColor(self._normalize_color(item.get("text_color") or "#000000")))
                
                lines_text = text.split("\n")
                total_text_h = len(lines_text) * font_size * 1.2
                
                start_y = y
                valign = (item.get("vertical_alignment") or "middle").lower()
                if valign == "bottom" and h > total_text_h:
                    start_y = y + h - total_text_h
                elif (valign == "center" or valign == "middle") and h > total_text_h:
                    start_y = y + (h - total_text_h) / 2
                elif valign == "top":
                    start_y = y

                for idx, lt in enumerate(lines_text):
                    line_w = c.stringWidth(lt, font_name, font_size)
                    align = (item.get("alignment") or "left").lower()
                    if align == "right":
                        tx = x + w - line_w - 2
                    elif align == "center":
                        tx = x + (w - line_w) / 2
                    else:
                        tx = x + 2
                    
                    line_y = start_y + font_size * (idx + 0.8)
                    c.drawString(tx, cy(line_y), lt)

        # Table cells text
        for table in tables:
            cells = table.get("cells") or []
            for cell in cells:
                ctext = cell.get("text", "")
                if ctext:
                    cx, cy_pos = float(cell.get("x", 0)), float(cell.get("y", 0))
                    cw, ch = float(cell.get("width", 0)), float(cell.get("height", 0))
                    
                    cfont_size = float(cell.get("font_size") or table.get("font_size") or 10.0)
                    font_name = "Helvetica"
                    cfont_weight = cell.get("font_weight") or table.get("font_weight") or "normal"
                    cfont_style = cell.get("font_style") or table.get("font_style") or "normal"
                    if "bold" in str(cfont_weight).lower():
                        font_name = "Helvetica-Bold"
                    if "italic" in str(cfont_style).lower():
                        font_name += "-Oblique" if "Bold" not in font_name else "Oblique"
                    
                    c.setFont(font_name, cfont_size)
                    c.setFillColor(HexColor(self._normalize_color(cell.get("text_color") or "#000000")))
                    
                    lines_text = ctext.split("\n")
                    total_text_h = len(lines_text) * cfont_size * 1.2
                    
                    start_y = cy_pos
                    valign = (cell.get("vertical_alignment") or table.get("vertical_alignment") or "middle").lower()
                    if valign == "bottom" and ch > total_text_h:
                        start_y = cy_pos + ch - total_text_h - 4
                    elif (valign == "center" or valign == "middle") and ch > total_text_h:
                        start_y = cy_pos + (ch - total_text_h) / 2
                    elif valign == "top":
                        start_y = cy_pos + 4

                    for idx, lt in enumerate(lines_text):
                        lt_w = c.stringWidth(lt, font_name, cfont_size)
                        align = (cell.get("alignment") or table.get("alignment") or "left").lower()
                        if align == "right":
                            tx = cx + cw - lt_w - 5
                        elif align == "center":
                            tx = cx + (cw - lt_w) / 2
                        else:
                            tx = cx + 5
                            
                        line_y = start_y + cfont_size * (idx + 0.8)
                        c.drawString(tx, cy(line_y), lt)

        # 8. Checkboxes & Radio buttons
        for cb in checkboxes:
            x, y, w, h = cb.get("x", 0), cb.get("y", 0), cb.get("width", 15), cb.get("height", 15)
            c.setStrokeColor(HexColor("#000000"))
            c.setLineWidth(1.0)
            c.rect(x, cy(y, h), w, h, fill=0, stroke=1)
            if cb.get("checked"):
                c.line(x, cy(y), x + w, cy(y + h))
                c.line(x, cy(y + h), x + w, cy(y))

        for rb in radio_buttons:
            x, y, w, h = rb.get("x", 0), rb.get("y", 0), rb.get("width", 15), rb.get("height", 15)
            r = min(w, h) / 2.0
            cx_pos, cy_pos = x + r, cy(y + r)
            c.setStrokeColor(HexColor("#000000"))
            c.setLineWidth(1.0)
            c.circle(cx_pos, cy_pos, r, fill=0, stroke=1)
            if rb.get("selected"):
                c.setFillColor(HexColor("#000000"))
                c.circle(cx_pos, cy_pos, r * 0.5, fill=1, stroke=0)

        # 9. Signatures
        for item in signatures:
            x, y, w, h = item.get("x", 0), item.get("y", 0), item.get("width", 100), item.get("height", 30)
            c.setStrokeColor(HexColor("#0000ff"))
            c.setLineWidth(1.0)
            c.rect(x, cy(y, h), w, h, fill=0, stroke=1)
            c.setFont("Helvetica-Oblique", 10)
            c.setFillColor(HexColor("#0000ff"))
            c.drawString(x + 5, cy(y, h) + 5, "[Signature Field]")

        # 10. Stamps
        for stamp in stamps:
            self._draw_stamp_pdf(c, cy, stamp)

        c.save()

    # PIL drawing helpers
    def _draw_image(self, img: Image.Image, item: Dict[str, Any]) -> None:
        """
        Draws a pure geometric placeholder for an image using coordinates.
        Never decodes, inspects, loads, or references image_data.
        """
        x = int(item.get("x", 0))
        y = int(item.get("y", 0))
        w = int(item.get("width", 0))
        h = int(item.get("height", 0))

        if w <= 0 or h <= 0:
            return

        try:
            draw = ImageDraw.Draw(img, "RGBA")
            # Check if this is a full-page background image
            page_w, page_h = img.size
            if x <= 5 and y <= 5 and w >= page_w - 10 and h >= page_h - 10:
                # Full page image: skip drawing placeholder, keep it clean
                return

            # Draw placeholder box
            draw.rectangle([x, y, x + w, y + h], fill=(240, 240, 240, 255), outline=(200, 200, 200, 255), width=1)
            # Draw diagonal lines crossing the box to geometrically signify an image
            draw.line([x, y, x + w, y + h], fill=(220, 220, 220, 255), width=1)
            draw.line([x, y + h, x + w, y], fill=(220, 220, 220, 255), width=1)
            # Draw label
            font = self._load_font("Arial", 8)
            draw.text((x + 5, y + 5), "[Image]", fill=(120, 120, 120, 255), font=font)
        except Exception as e:
            print(f"[FormRenderer] Failed to render image placeholder: {e}")

    def _draw_rectangle(self, draw: ImageDraw.ImageDraw, item: Dict[str, Any]) -> None:
        x = float(item.get("x", 0))
        y = float(item.get("y", 0))
        w = float(item.get("width", 0))
        h = float(item.get("height", 0))

        fill = item.get("fill_color") or item.get("background_color")
        stroke = item.get("stroke_color") or item.get("border_color")
        stroke_w = float(item.get("stroke_width") or item.get("border_thickness") or 1.0)

        fill_color = self._normalize_color_rgba(fill) if fill else None
        stroke_color = self._normalize_color_rgba(stroke) if stroke else None

        draw.rectangle(
            [x, y, x + w, y + h],
            fill=fill_color,
            outline=stroke_color,
            width=int(stroke_w)
        )

    def _draw_line(self, draw: ImageDraw.ImageDraw, item: Dict[str, Any]) -> None:
        x1 = float(item.get("x1", item.get("x", 0)))
        y1 = float(item.get("y1", item.get("y", 0)))
        x2 = float(item.get("x2", x1 + item.get("width", 0)))
        y2 = float(item.get("y2", y1 + item.get("height", 0)))

        stroke = item.get("stroke_color") or "#000000"
        stroke_w = float(item.get("stroke_width", 1.0))
        stroke_color = self._normalize_color_rgba(stroke)

        draw.line([x1, y1, x2, y2], fill=stroke_color, width=int(stroke_w))

    def _draw_checkbox(self, draw: ImageDraw.ImageDraw, item: Dict[str, Any]) -> None:
        x = float(item.get("x", 0))
        y = float(item.get("y", 0))
        w = float(item.get("width", 15))
        h = float(item.get("height", 15))

        stroke_color = self._normalize_color_rgba(item.get("stroke_color") or "#000000")
        fill_color = self._normalize_color_rgba(item.get("fill_color")) if item.get("fill_color") else None

        draw.rectangle([x, y, x + w, y + h], fill=fill_color, outline=stroke_color, width=1)

        if item.get("checked"):
            # Draw X inside the checkbox
            draw.line([x + 2, y + 2, x + w - 2, y + h - 2], fill=stroke_color, width=1)
            draw.line([x + 2, y + h - 2, x + w - 2, y + 2], fill=stroke_color, width=1)

    def _draw_radio_button(self, draw: ImageDraw.ImageDraw, item: Dict[str, Any]) -> None:
        x = float(item.get("x", 0))
        y = float(item.get("y", 0))
        w = float(item.get("width", 15))
        h = float(item.get("height", 15))

        stroke_color = self._normalize_color_rgba(item.get("stroke_color") or "#000000")
        fill_color = self._normalize_color_rgba(item.get("fill_color")) if item.get("fill_color") else None

        draw.ellipse([x, y, x + w, y + h], fill=fill_color, outline=stroke_color, width=1)

        if item.get("selected"):
            # Draw a solid inner circle
            padding = min(w, h) * 0.25
            draw.ellipse(
                [x + padding, y + padding, x + w - padding, y + h - padding],
                fill=stroke_color,
                outline=None
            )

    def _draw_signature(self, draw: ImageDraw.ImageDraw, item: Dict[str, Any]) -> None:
        x = float(item.get("x", 0))
        y = float(item.get("y", 0))
        w = float(item.get("width", 120))
        h = float(item.get("height", 35))

        stroke_color = self._normalize_color_rgba(item.get("stroke_color") or "#0000ff")
        draw.rectangle([x, y, x + w, y + h], fill=None, outline=stroke_color, width=1)

        # Draw a cursive-like placeholder or tag
        font = self._load_font("Arial", 9)
        draw.text((x + 5, y + h - 15), "[Signature Field]", fill=stroke_color, font=font)

    def _word_wrap(self, text: str, font: ImageFont.ImageFont, max_width: float, draw: ImageDraw.ImageDraw) -> list:
        """Wrap text to fit within max_width pixels, preserving explicit newlines."""
        if max_width <= 0:
            return text.split("\n")

        result_lines = []
        for paragraph in text.split("\n"):
            if not paragraph.strip():
                result_lines.append("")
                continue

            words = paragraph.split()
            if not words:
                result_lines.append("")
                continue

            current_line = words[0]
            for word in words[1:]:
                test_line = current_line + " " + word
                try:
                    l, t, r, b = draw.textbbox((0, 0), test_line, font=font)
                    line_w = r - l
                except Exception:
                    line_w = len(test_line) * 7

                if line_w <= max_width:
                    current_line = test_line
                else:
                    result_lines.append(current_line)
                    current_line = word

            result_lines.append(current_line)

        return result_lines

    def _draw_text(self, draw: ImageDraw.ImageDraw, item: Dict[str, Any]) -> None:
        x = float(item.get("x", 0))
        y = float(item.get("y", 0))
        w = float(item.get("width", 0))
        h = float(item.get("height", 0))
        text = item.get("text", "")
        if not text:
            return

        font_size = float(item.get("font_size") or 11.0)
        if ("font_size" not in item or item["font_size"] == 11.0) and h > 12.0:
            font_size = max(8.0, min(72.0, h * 0.75))

        font_family = item.get("font_family") or "Arial"
        font_weight = item.get("font_weight") or "normal"
        font_style = item.get("font_style") or "normal"
        text_color = self._normalize_color_rgba(item.get("text_color") or "#000000")
        background_color = item.get("background_color")

        if background_color and w > 0 and h > 0:
            draw.rectangle(
                [x, y, x + w, y + h],
                fill=self._normalize_color_rgba(background_color)
            )

        padding_x = 5
        usable_w = max(1, w - 2 * padding_x) if w > 0 else 0

        # Shrink-to-fit: word-wrap and reduce font size until text fits within bounding box
        if w > 0 and h > 0:
            min_font = 6.0
            while font_size >= min_font:
                font = self._load_font(font_family, font_size, font_weight, font_style)
                wrapped_lines = self._word_wrap(text, font, usable_w, draw)
                line_height = font_size * 1.2
                total_text_h = len(wrapped_lines) * line_height
                if total_text_h <= h:
                    break
                font_size -= 0.5
            else:
                # Hit minimum font size — use it regardless of overflow
                font_size = min_font
                font = self._load_font(font_family, font_size, font_weight, font_style)
                wrapped_lines = self._word_wrap(text, font, usable_w, draw)
                line_height = font_size * 1.2
                total_text_h = len(wrapped_lines) * line_height
        else:
            font = self._load_font(font_family, font_size, font_weight, font_style)
            wrapped_lines = text.split("\n")
            line_height = font_size * 1.2
            total_text_h = len(wrapped_lines) * line_height

        start_y = y
        if w > 0 and h > 0:
            valign = (item.get("vertical_alignment") or "middle").lower()
            if valign == "bottom" and h > total_text_h:
                start_y = y + h - total_text_h - 2
            elif (valign == "center" or valign == "middle") and h > total_text_h:
                start_y = y + (h - total_text_h) / 2
            elif valign == "top":
                start_y = y + 2
        else:
            valign = "top"

        for idx, lt in enumerate(wrapped_lines):
            if not lt:
                continue
            try:
                left_box, top_box, right_box, bottom_box = draw.textbbox((0, 0), lt, font=font)
                lt_w = right_box - left_box
            except Exception:
                lt_w = len(lt) * font_size * 0.6

            tx = x
            if w > 0:
                align = (item.get("alignment") or "left").lower()
                if align == "right":
                    tx = x + w - lt_w - padding_x
                elif align == "center":
                    tx = x + (w - lt_w) / 2
                else:
                    tx = x + padding_x
            else:
                tx = x

            line_y = start_y + idx * line_height
            draw.text((tx, line_y), lt, fill=text_color, font=font)

    def _draw_table(self, draw: ImageDraw.ImageDraw, img: Image.Image, item: Dict[str, Any]) -> None:
        # Draw cells
        cells = item.get("cells") or []
        for cell in cells:
            cx = float(cell.get("x", 0))
            cy = float(cell.get("y", 0))
            cw = float(cell.get("width", 0))
            ch = float(cell.get("height", 0))

            fill = cell.get("fill_color") or cell.get("background_color")
            if fill:
                draw.rectangle([cx, cy, cx + cw, cy + ch], fill=self._normalize_color_rgba(fill))

            # Draw cell text
            ctext = cell.get("text", "")
            if ctext:
                cfont_size = float(cell.get("font_size") or item.get("font_size") or 10.0)
                cfont_family = cell.get("font_family") or item.get("font_family") or "Arial"
                ctext_color = self._normalize_color_rgba(cell.get("text_color") or "#000000")
                cfont_weight = cell.get("font_weight") or item.get("font_weight") or "normal"
                cfont_style = cell.get("font_style") or item.get("font_style") or "normal"
                font = self._load_font(cfont_family, cfont_size, cfont_weight, cfont_style)
                
                try:
                    left_box, top_box, right_box, bottom_box = draw.textbbox((0, 0), ctext, font=font)
                    text_w = right_box - left_box
                    text_h = bottom_box - top_box
                except Exception:
                    text_w = len(ctext) * cfont_size * 0.6
                    text_h = cfont_size

                align = (cell.get("alignment") or item.get("alignment") or "left").lower()
                if align == "right":
                    tx = cx + cw - text_w - 5
                elif align == "center":
                    tx = cx + (cw - text_w) / 2
                else:
                    tx = cx + 5

                valign = (cell.get("vertical_alignment") or item.get("vertical_alignment") or "middle").lower()
                if valign == "bottom":
                    ty = cy + ch - text_h - 5
                elif valign == "top":
                    ty = cy + 5
                else:
                    ty = cy + (ch - text_h) / 2

                draw.text((tx, ty), ctext, fill=ctext_color, font=font)

        # Draw grid lines
        grid_lines = item.get("grid_lines") or []
        for line in grid_lines:
            lx1 = float(line.get("x1", line.get("x", 0)))
            ly1 = float(line.get("y1", line.get("y", 0)))
            lx2 = float(line.get("x2", lx1 + line.get("width", 0)))
            ly2 = float(line.get("y2", ly1 + line.get("height", 0)))
            stroke = line.get("stroke_color") or item.get("stroke_color") or "#000000"
            stroke_w = float(line.get("stroke_width") or item.get("stroke_width") or 1.0)
            
            draw.line([lx1, ly1, lx2, ly2], fill=self._normalize_color_rgba(stroke), width=int(stroke_w))

    def _draw_table_pdf(self, c: Any, cy_func: Any, item: Dict[str, Any]) -> None:
        from reportlab.lib.colors import HexColor

        cells = item.get("cells") or []
        for cell in cells:
            cx, cy_pos = float(cell.get("x", 0)), float(cell.get("y", 0))
            cw, ch = float(cell.get("width", 0)), float(cell.get("height", 0))
            fill = cell.get("fill_color") or cell.get("background_color")
            if fill:
                c.setFillColor(HexColor(self._normalize_color(fill)))
                c.rect(cx, cy_func(cy_pos, ch), cw, ch, fill=1, stroke=0)

            ctext = cell.get("text", "")
            if ctext:
                cfont_size = float(cell.get("font_size") or 10.0)
                font_name = "Helvetica"
                cfont_weight = cell.get("font_weight") or item.get("font_weight") or "normal"
                cfont_style = cell.get("font_style") or item.get("font_style") or "normal"
                if "bold" in str(cfont_weight).lower():
                    font_name = "Helvetica-Bold"
                if "italic" in str(cfont_style).lower():
                    font_name += "-Oblique" if "Bold" not in font_name else "Oblique"
                c.setFont(font_name, cfont_size)
                c.setFillColor(HexColor(self._normalize_color(cell.get("text_color") or "#000000")))

                align = (cell.get("alignment") or item.get("alignment") or "left").lower()
                valign = (cell.get("vertical_alignment") or item.get("vertical_alignment") or "middle").lower()
                
                text_w = c.stringWidth(ctext, font_name, cfont_size)
                text_h = cfont_size

                if align == "right":
                    tx = cx + cw - text_w - 5
                elif align == "center":
                    tx = cx + (cw - text_w) / 2
                else:
                    tx = cx + 5

                if valign == "bottom":
                    ty = cy_pos + ch - text_h - 4
                elif valign == "top":
                    ty = cy_pos + 4
                else:
                    ty = cy_pos + (ch - text_h) / 2

                c.drawString(tx, cy_func(ty + text_h), ctext)

        grid_lines = item.get("grid_lines") or []
        for line in grid_lines:
            lx1, ly1 = float(line.get("x1", line.get("x", 0))), float(line.get("y1", line.get("y", 0)))
            lx2, ly2 = float(line.get("x2", lx1 + line.get("width", 0))), float(line.get("y2", ly1 + line.get("height", 0)))
            stroke = line.get("stroke_color") or item.get("stroke_color") or "#000000"
            stroke_w = float(line.get("stroke_width") or 1.0)
            c.setStrokeColor(HexColor(self._normalize_color(stroke)))
            c.setLineWidth(stroke_w)
            c.line(lx1, cy_func(ly1), lx2, cy_func(ly2))

    # Color normalization helpers
    def _normalize_color(self, color: Any, default: str = "#000000") -> str:
        if not color:
            return default
        color_str = str(color).strip()
        if color_str.startswith("#"):
            # Hex values can sometimes be shorthand or have extra characters
            if len(color_str) in {4, 7}:
                return color_str
            if len(color_str) > 7:
                return color_str[:7]
        # Check if fitz-like tuple color (r,g,b)
        if color_str.startswith("(") and color_str.endswith(")"):
            try:
                parts = [float(p) for p in color_str[1:-1].split(",")]
                if len(parts) >= 3:
                    # check if floats 0.0-1.0 or ints 0-255
                    if all(0.0 <= p <= 1.0 for p in parts[:3]):
                        r, g, b = [int(p * 255) for p in parts[:3]]
                    else:
                        r, g, b = [int(p) for p in parts[:3]]
                    return f"#{r:02x}{g:02x}{b:02x}"
            except Exception:
                pass
        return color_str

    def _normalize_color_rgba(self, color: Any) -> tuple:
        hex_color = self._normalize_color(color, default="#000000")
        try:
            if hex_color.startswith("#"):
                h = hex_color.lstrip("#")
                if len(h) == 3:
                    h = "".join(c * 2 for c in h)
                rgb = tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
                return rgb + (255,)
        except Exception:
            pass
        return (0, 0, 0, 255)

    # Font loader helper
    def _load_font(
        self,
        font_family: str,
        size: float,
        weight: str = "normal",
        style: str = "normal"
    ) -> ImageFont.ImageFont:
        font_size = int(max(1.0, size))
        font_map = {
            "arial": ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"],
            "helvetica": ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"],
            "times": ["times.ttf", "Times.ttf", "DejaVuSerif.ttf"],
            "courier": ["cour.ttf", "Courier.ttf", "DejaVuSansMono.ttf"],
            "calibri": ["calibri.ttf", "Calibri.ttf"],
            "cambria": ["cambriab.ttf", "Cambria.ttf"],
        }

        # Handle bold/italic styles
        font_suffix = ""
        if "bold" in weight.lower() and "italic" in style.lower():
            font_suffix = "bi"
        elif "bold" in weight.lower():
            font_suffix = "bd"
        elif "italic" in style.lower():
            font_suffix = "i"

        family_key = font_family.lower()
        candidates = []
        
        if family_key in font_map:
            for name in font_map[family_key]:
                if font_suffix:
                    base, ext = os.path.splitext(name)
                    candidates.append(f"{base}{font_suffix}{ext}")
                candidates.append(name)
        else:
            candidates.append(font_family)
            candidates.append(f"{font_family}.ttf")

        # Try default paths
        search_paths = [
            "",
            "C:\\Windows\\Fonts\\",
            "/usr/share/fonts/truetype/",
            "/usr/share/fonts/TTF/",
            "/usr/share/fonts/"
        ]

        for path in search_paths:
            for cand in candidates:
                full_path = os.path.join(path, cand)
                if os.path.exists(full_path) and os.path.isfile(full_path):
                    try:
                        return ImageFont.truetype(full_path, font_size)
                    except Exception:
                        pass

        # Fallback to predefined user default font path
        if self.default_font_path and os.path.exists(self.default_font_path):
            try:
                return ImageFont.truetype(self.default_font_path, font_size)
            except Exception:
                pass

        # absolute default fallback
        return ImageFont.load_default()

    def _draw_stamp(self, draw: ImageDraw.ImageDraw, item: Dict[str, Any]) -> None:
        x = float(item.get("x", 0))
        y = float(item.get("y", 0))
        w = float(item.get("width", 120))
        h = float(item.get("height", 120))
        if w <= 0 or h <= 0:
            return
        
        # Stamps are usually red or blue
        color_raw = item.get("border_color") or item.get("stroke_color") or "#d9381e"
        color = self._normalize_color_rgba(color_raw)
        
        draw.ellipse([x, y, x + w, y + h], outline=color, width=3)
        draw.ellipse([x + 4, y + 4, x + w - 4, y + h - 4], outline=color, width=1)
        
        text = item.get("text") or "STAMP / SEAL"
        font_size = float(item.get("font_size") or 10.0)
        font = self._load_font("Arial", font_size, weight="bold")
        
        try:
            left_box, top_box, right_box, bottom_box = draw.textbbox((0, 0), text, font=font)
            text_w = right_box - left_box
            text_h = bottom_box - top_box
        except Exception:
            text_w = len(text) * font_size * 0.6
            text_h = font_size
            
        tx = x + (w - text_w) / 2
        ty = y + (h - text_h) / 2
        draw.text((tx, ty), text, fill=color, font=font)

    def _draw_stamp_pdf(self, c: Any, cy_func: Any, item: Dict[str, Any]) -> None:
        from reportlab.lib.colors import HexColor
        x, y = float(item.get("x", 0)), float(item.get("y", 0))
        w, h = float(item.get("width", 120)), float(item.get("height", 120))
        if w <= 0 or h <= 0:
            return
        
        color_raw = item.get("border_color") or item.get("stroke_color") or "#d9381e"
        color_hex = self._normalize_color(color_raw)
        
        c.setStrokeColor(HexColor(color_hex))
        c.setLineWidth(3.0)
        c.ellipse(x, cy_func(y, h), w, h, fill=0, stroke=1)
        
        c.setLineWidth(1.0)
        c.ellipse(x + 4, cy_func(y + 4, h - 8), w - 8, h - 8, fill=0, stroke=1)
        
        text = item.get("text") or "STAMP / SEAL"
        font_size = float(item.get("font_size") or 10.0)
        c.setFont("Helvetica-Bold", font_size)
        c.setFillColor(HexColor(color_hex))
        
        text_w = c.stringWidth(text, "Helvetica-Bold", font_size)
        tx = x + (w - text_w) / 2
        ty = y + (h - font_size) / 2
        
        c.drawString(tx, cy_func(ty + font_size), text)
