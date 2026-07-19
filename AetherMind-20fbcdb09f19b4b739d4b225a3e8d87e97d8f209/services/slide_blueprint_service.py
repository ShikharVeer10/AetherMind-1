"""
SlideBlueprintService — produces a structured, LLM-optimised JSON blueprint
from an extracted SlideModel so that a downstream LLM can regenerate the slide
with near-identical layout, text, and styling.

Key capabilities:
  1. Spatial text clustering   → merges fragmented OCR boxes into coherent
     content blocks using proximity-based grouping.
  2. Section detection         → assigns semantic roles (title, info_card,
     body_section, footer, …) based on y-position bands & background colour.
  3. Design token extraction   → captures dominant colours, font hierarchy,
     backgrounds.
  4. Verbatim text dump        → flat list of every visible string.
  5. Compact reconstruction prompt → embedded natural-language instructions that
     reference the structured data fields.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from models.document_model import DocumentModel, SlideModel, DocumentElementModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text_of(element: DocumentElementModel) -> str:
    """Return the best text representation of an element."""
    text = (element.text or "").strip()
    if not text and element.paragraphs:
        text = " ".join(p.text.strip() for p in element.paragraphs if p.text).strip()
    return text


def _is_garbled(text: str, threshold: float = 0.45) -> bool:
    """Heuristic: if more than `threshold` fraction of alpha chars are lowercase
    vowel-free clusters of ≥ 4 consonants in a row, flag as garbled OCR."""
    if len(text) < 3:
        return True
    alpha_chars = [c for c in text if c.isalpha()]
    if not alpha_chars:
        return False
    consonant_runs = re.findall(r'[^aeiouAEIOU\s\d]{4,}', text)
    garbled_chars = sum(len(r) for r in consonant_runs)
    return garbled_chars / max(len(alpha_chars), 1) > threshold


def _element_center(element: DocumentElementModel) -> Tuple[float, float]:
    p = element.position
    return (p.x + p.width / 2, p.y + p.height / 2)


def _element_font_size(element: DocumentElementModel) -> float:
    """Estimate font size from element style or bounding box height."""
    if element.style and element.style.font_size:
        return element.style.font_size
    # Rough heuristic: box height as proxy
    return element.position.height


# ---------------------------------------------------------------------------
# Core Service
# ---------------------------------------------------------------------------

class SlideBlueprintService:
    """Builds a compact, structured JSON blueprint from extracted slide data."""

    # Vertical band thresholds (as fraction of canvas height)
    TITLE_BAND_MAX = 0.12       # Top 12 % → title zone
    HEADER_BAND_MAX = 0.25      # 12–25 % → header / info-card zone
    FOOTER_BAND_MIN = 0.88      # Bottom 12 % → footer zone

    # Spatial proximity thresholds for OCR text grouping (pixels)
    CLUSTER_X_GAP = 60          # Max horizontal gap to merge boxes
    CLUSTER_Y_GAP = 20          # Max vertical gap to merge boxes in same line
    BLOCK_Y_GAP = 40            # Max vertical gap to group lines into a block

    def build_blueprint(self, document: DocumentModel) -> Dict[str, Any]:
        """Build the full document blueprint."""
        slides = []
        for slide in document.slides:
            slides.append(self._build_slide_blueprint(slide))

        return {
            "document_name": document.document_name,
            "document_type": document.document_type,
            "slide_count": document.total_slides,
            "slides": slides,
        }
    def _build_slide_blueprint(self, slide: SlideModel) -> Dict[str, Any]:
        canvas = self._detect_canvas(slide)
        cw, ch = canvas["width"], canvas["height"]
        text_elements = self._collect_text_elements(slide)
        cards = [e for e in slide.elements if e.element_type in ("shape", "rectangle")]
        content_blocks = self._cluster_into_blocks(text_elements, cw, ch, cards=cards)
        sections = self._detect_sections(content_blocks, slide, cw, ch)
        table_sections = self._extract_table_sections(slide, cw, ch)
        sections.extend(table_sections)
        chart_sections = self._extract_chart_sections(slide, cw, ch)
        sections.extend(chart_sections)
        sections.sort(key=lambda s: s.get("position", {}).get("y_pct", 0))
        design = self._extract_design_tokens(slide, cw, ch)

        # 1. Professional Paragraph Copy-writing & Rewriting (Phase 3 text polishing)
        for s in sections:
            if s.get("role") != "table":
                if "content" in s:
                    for item in s["content"]:
                        if "text" in item:
                            item["text"] = self._rewrite_text_professionally(item["text"])
                if "heading" in s and s["heading"]:
                    s["heading"] = self._rewrite_text_professionally(s["heading"])

        # 2. Populate Phase 4 Structure Fields
        for idx, s in enumerate(sections):
            role = s.get("role", "body_section").lower()
            
            # Purpose
            purpose = "Explanation"
            if "title" in role:
                purpose = "Title"
            elif "header" in role:
                purpose = "Introduction"
            elif "table" in role:
                purpose = "Comparison"
            elif "chart" in role:
                purpose = "Summary"
            elif "flowchart" in role or "process" in role:
                purpose = "Process"
            s["purpose"] = purpose
            
            # Subheading
            s["subheading"] = s.get("subheading") or None
            
            # Visual Role
            visual_role = "Card"
            if "title" in role:
                visual_role = "Title"
            elif "table" in role:
                visual_role = "Table"
            elif "chart" in role:
                visual_role = "Infographic"
            s["visual_role"] = visual_role
            
            # Importance
            importance = "medium"
            if "title" in role or "heading" in role or "chart" in role:
                importance = "high"
            s["importance"] = importance
            
            # Semantic Role
            semantic_role = "Explanation"
            if "title" in role:
                semantic_role = "Title"
            elif "process" in role or "step" in role:
                semantic_role = "Numbered process"
            elif "callout" in role or "alert" in role:
                semantic_role = "Callout"
            s["semantic_role"] = semantic_role
            
            # Reading Order
            s["reading_order"] = idx + 1

        # 3. Extract process steps (Phase 5)
        process_steps = self._extract_process_steps(slide)

        # 4. Extract illustration/image understanding (Phase 6)
        img_und = {
            "objects": [],
            "illustrations": [],
            "icons": [],
            "diagrams": [],
            "semantic_meaning": "",
            "reconstruction_metadata": {}
        }
        if slide.image_understanding:
            img_und["objects"] = slide.image_understanding.objects_detected or []
            img_und["illustrations"] = slide.image_understanding.visual_elements or []
            img_und["semantic_meaning"] = slide.image_understanding.semantic_meaning or ""
            if slide.image_understanding.visual_design:
                vd = slide.image_understanding.visual_design
                img_und["reconstruction_metadata"] = {
                    "color_scheme": vd.color_scheme,
                    "shapes": vd.shapes,
                    "layout_pattern": vd.layout_pattern,
                    "background_style": vd.background_style,
                    "visual_style_description": "Clean flat vector illustration style."
                }
        else:
            img_und["reconstruction_metadata"] = {
                "color_scheme": design.get("primary_colors", []) + design.get("accent_colors", []),
                "shapes": ["rectangle"],
                "layout_pattern": "grid",
                "visual_style_description": "Flat vector infographic illustration style."
            }

        # 5. Extract reconstruction payload for visual objects (Phase 8)
        visual_objects_payload = []
        for e in slide.elements:
            left_pct = (e.position.x / cw) * 100 if cw > 0 else 0.0
            top_pct = (e.position.y / ch) * 100 if ch > 0 else 0.0
            width_pct = (e.position.width / cw) * 100 if cw > 0 else 0.0
            height_pct = (e.position.height / ch) * 100 if ch > 0 else 0.0
            
            raw_text = e.text
            rewritten_text = self._rewrite_text_professionally(raw_text) if raw_text else ""
            
            style_dict = {}
            if e.style:
                style_dict = {
                    "font_name": e.style.font_name,
                    "font_size": e.style.font_size,
                    "bold": e.style.bold,
                    "italic": e.style.italic,
                    "underline": e.style.underline,
                    "text_color": e.style.text_color,
                    "background_color": e.style.background_color,
                    "alignment": e.style.alignment,
                    "vertical_alignment": e.style.vertical_alignment,
                    "border_color": e.style.border_color,
                    "border_thickness": e.style.border_thickness,
                    "border_radius": e.style.border_radius,
                    "opacity": e.style.opacity,
                    "shadow": e.style.shadow,
                    "gradient": e.style.gradient,
                    "padding": e.style.padding,
                }
            
            visual_objects_payload.append({
                "element_id": e.element_id,
                "element_type": e.element_type,
                "shape_type": e.shape_type or "rectangle",
                "text": rewritten_text or None,
                "absolute_coordinates": {
                    "x": e.position.x,
                    "y": e.position.y,
                    "width": e.position.width,
                    "height": e.position.height
                },
                "percentage_coordinates": {
                    "left": round(left_pct, 2),
                    "top": round(top_pct, 2),
                    "width": round(width_pct, 2),
                    "height": round(height_pct, 2)
                },
                "width": e.position.width,
                "height": e.position.height,
                "z_order": e.metadata.get("z_order") or e.stacking_order or 0,
                "alignment": e.style.alignment if e.style else "left",
                "anchor": e.anchor_point or "top-left",
                "rotation": e.metadata.get("rotation") or 0.0,
                "padding": e.style.padding if e.style else {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0},
                "margin": {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0},
                "parent_container": e.parent,
                "group": e.group_id,
                "style": style_dict,
                "background": {
                    "fill_color": e.metadata.get("fill_color") or (e.style.background_color if e.style else None),
                    "gradient": e.gradient or e.metadata.get("gradient"),
                    "opacity": e.opacity or e.metadata.get("opacity") or 1.0
                },
                "border": {
                    "color": e.metadata.get("border_color") or (e.style.border_color if e.style else None),
                    "thickness": e.metadata.get("border_thickness") or (e.style.border_thickness if e.style else None),
                    "radius": e.border_radius or e.metadata.get("border_radius")
                },
                "shadow": e.shadow or e.metadata.get("shadow"),
                "text_style": {
                    "font_family": e.style.font_name if e.style else "Arial",
                    "font_size": e.style.font_size if e.style else 12.0,
                    "bold": e.style.bold if e.style else False,
                    "italic": e.style.italic if e.style else False,
                    "underline": e.underline or (e.style.underline if e.style else False),
                    "color": e.style.text_color if e.style else "#000000"
                },
                "semantic_meaning": e.metadata.get("semantic_meaning") or f"Visual object representing a {e.element_type} of type {e.shape_type or 'rect'}."
            })

        all_text = [self._rewrite_text_professionally(t) for t in self._collect_all_verbatim_text(slide)]
        reconstruction_prompt = self._build_reconstruction_prompt(
            slide, sections, design, all_text, canvas
        )

        return {
            "slide_number": slide.slide_number,
            "title": slide.title,
            "canvas": canvas,
            "design_tokens": design,
            "sections": sections,
            "process_steps": process_steps,
            "image_understanding": img_und,
            "reconstruction_payload": visual_objects_payload,
            "all_text_verbatim": all_text,
            "reconstruction_prompt": reconstruction_prompt,
            "reconstruction_prompt_designer": self._build_professional_designer_prompt(
                slide, sections, design, canvas
            ),
        }

    def _detect_canvas(self, slide: SlideModel) -> Dict[str, Any]:
        """Determine canvas dimensions from elements."""
        max_x = 0.0
        max_y = 0.0
        for e in slide.elements:
            if e.position:
                max_x = max(max_x, e.position.x + e.position.width)
                max_y = max(max_y, e.position.y + e.position.height)

        if max_x > 100000:  # EMU coordinates
            width = max(max_x, 12192000.0)
            height = max(max_y, 6858000.0)
        else:
            width = max(max_x, 1920.0)
            height = max(max_y, 1080.0)

        ratio = width / height if height > 0 else 1.78
        if abs(ratio - 16 / 9) < 0.1:
            aspect = "16:9"
        elif abs(ratio - 4 / 3) < 0.1:
            aspect = "4:3"
        else:
            aspect = f"{ratio:.2f}:1"

        return {
            "width": round(width, 1),
            "height": round(height, 1),
            "aspect_ratio": aspect,
        }

    def _collect_text_elements(
        self, slide: SlideModel
    ) -> List[DocumentElementModel]:
        """Filter to text elements with meaningful content."""
        result = []
        for e in slide.elements:
            if e.element_type in ("image",):
                continue
            text = _text_of(e)
            if not text:
                continue
            # Skip very short garbled fragments (< 3 real chars)
            clean = re.sub(r'\s+', '', text)
            if len(clean) < 2:
                continue
            result.append(e)
        return result

    def _cluster_into_blocks(
        self,
        elements: List[DocumentElementModel],
        canvas_w: float,
        canvas_h: float,
        cards: Optional[List[DocumentElementModel]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Cluster nearby text elements into logical content blocks.

        Algorithm:
        1. Sort elements top-to-bottom, left-to-right.
        2. Group elements into horizontal lines (small y-gap).
        3. Merge adjacent lines into vertical blocks (medium y-gap).
        """
        if not elements:
            return []

        scale = 1.0
        if canvas_w > 100000:  # EMU
            scale = canvas_w / 1920.0

        x_gap = self.CLUSTER_X_GAP * scale
        y_gap = self.CLUSTER_Y_GAP * scale
        block_y_gap = self.BLOCK_Y_GAP * scale

        # Map text element to containing card element ID
        elem_to_card = {}
        if cards:
            for elem in elements:
                cx = elem.position.x + elem.position.width / 2
                cy = elem.position.y + elem.position.height / 2
                for card in cards:
                    p = card.position
                    if p.x <= cx <= p.x + p.width and p.y <= cy <= p.y + p.height:
                        elem_to_card[elem.element_id] = card.element_id
                        break

        # Sort by Y then X
        sorted_elems = sorted(
            elements,
            key=lambda e: (e.position.y, e.position.x),
        )

        # Step 1: Group into horizontal lines (constrained by containing card)
        lines: List[List[DocumentElementModel]] = []
        current_line: List[DocumentElementModel] = [sorted_elems[0]]

        for elem in sorted_elems[1:]:
            last = current_line[-1]
            last_cy = last.position.y + last.position.height / 2
            elem_cy = elem.position.y + elem.position.height / 2
            
            elem_card = elem_to_card.get(elem.element_id)
            last_card = elem_to_card.get(last.element_id)
            
            if abs(elem_cy - last_cy) <= y_gap and elem_card == last_card:
                current_line.append(elem)
            else:
                lines.append(current_line)
                current_line = [elem]
        lines.append(current_line)

        # Step 2: Sort each line left-to-right and merge text
        merged_lines: List[Dict[str, Any]] = []
        for line_elems in lines:
            line_elems.sort(key=lambda e: e.position.x)
            merged_text = " ".join(_text_of(e) for e in line_elems).strip()
            min_x = min(e.position.x for e in line_elems)
            min_y = min(e.position.y for e in line_elems)
            max_x = max(e.position.x + e.position.width for e in line_elems)
            max_y = max(e.position.y + e.position.height for e in line_elems)
            avg_font = sum(_element_font_size(e) for e in line_elems) / len(line_elems)

            # Collect style info from the first styled element
            style_info = {}
            for e in line_elems:
                if e.style:
                    if e.style.font_size:
                        style_info["font_size"] = e.style.font_size
                    if e.style.bold:
                        style_info["bold"] = True
                    if e.style.text_color:
                        style_info["text_color"] = e.style.text_color
                    if e.style.background_color:
                        style_info["background_color"] = e.style.background_color
                    break

            merged_lines.append({
                "text": merged_text,
                "x": min_x,
                "y": min_y,
                "width": max_x - min_x,
                "height": max_y - min_y,
                "avg_font_size": avg_font,
                "element_ids": [e.element_id for e in line_elems],
                "style": style_info,
            })

        # Step 3: Group lines into vertical blocks (constrained by containing card)
        blocks: List[Dict[str, Any]] = []
        current_block_lines: List[Dict[str, Any]] = [merged_lines[0]]

        for line in merged_lines[1:]:
            prev_line = current_block_lines[-1]
            prev_bottom = prev_line["y"] + prev_line["height"]
            gap = line["y"] - prev_bottom

            # Check if lines are horizontally aligned (similar x-range)
            x_overlap = (
                min(prev_line["x"] + prev_line["width"], line["x"] + line["width"])
                - max(prev_line["x"], line["x"])
            )
            horizontally_related = x_overlap > 0.3 * min(
                prev_line["width"], line["width"]
            )

            prev_line_card = None
            if prev_line["element_ids"] and elem_to_card:
                prev_line_card = elem_to_card.get(prev_line["element_ids"][0])
                
            line_card = None
            if line["element_ids"] and elem_to_card:
                line_card = elem_to_card.get(line["element_ids"][0])

            if gap <= block_y_gap and horizontally_related and prev_line_card == line_card:
                current_block_lines.append(line)
            else:
                blocks.append(self._merge_lines_to_block(current_block_lines, canvas_w, canvas_h))
                current_block_lines = [line]

        blocks.append(self._merge_lines_to_block(current_block_lines, canvas_w, canvas_h))

        return blocks

    def _merge_lines_to_block(
        self,
        lines: List[Dict[str, Any]],
        canvas_w: float,
        canvas_h: float,
    ) -> Dict[str, Any]:
        """Merge a group of text lines into a single content block."""
        text_parts = [l["text"] for l in lines if l["text"]]
        merged_text = "\n".join(text_parts)

        min_x = min(l["x"] for l in lines)
        min_y = min(l["y"] for l in lines)
        max_x = max(l["x"] + l["width"] for l in lines)
        max_y = max(l["y"] + l["height"] for l in lines)
        avg_font = sum(l["avg_font_size"] for l in lines) / len(lines) if lines else 12

        all_ids = []
        for l in lines:
            all_ids.extend(l["element_ids"])

        # Collect style from the most prominent line (largest font)
        best_style = {}
        for l in sorted(lines, key=lambda x: x["avg_font_size"], reverse=True):
            if l.get("style"):
                best_style = l["style"]
                break

        return {
            "text": merged_text,
            "position": {
                "x_pct": round(100 * min_x / canvas_w, 1) if canvas_w else 0,
                "y_pct": round(100 * min_y / canvas_h, 1) if canvas_h else 0,
                "width_pct": round(100 * (max_x - min_x) / canvas_w, 1) if canvas_w else 0,
                "height_pct": round(100 * (max_y - min_y) / canvas_h, 1) if canvas_h else 0,
            },
            "avg_font_size": round(avg_font, 1),
            "line_count": len(lines),
            "element_ids": all_ids,
            "style": best_style,
        }

    # ------------------------------------------------------------------
    # Section detection
    # ------------------------------------------------------------------

    def _detect_sections(
        self,
        blocks: List[Dict[str, Any]],
        slide: SlideModel,
        canvas_w: float,
        canvas_h: float,
    ) -> List[Dict[str, Any]]:
        """Assign semantic roles to content blocks based on position and content."""
        sections: List[Dict[str, Any]] = []

        for i, block in enumerate(blocks):
            y_frac = block["position"]["y_pct"] / 100.0
            text = block["text"]
            font_size = block["avg_font_size"]
            style = block.get("style", {})

            role = self._classify_block_role(
                text, y_frac, font_size, style, blocks, i
            )

            section: Dict[str, Any] = {
                "id": f"section_{i}",
                "role": role,
                "position": block["position"],
            }

            # If the block looks like key-value pairs (label: value), structure them
            kv_pairs = self._extract_key_value_pairs(text)
            if kv_pairs and role in ("metadata_row", "info_card", "body_section"):
                section["children"] = kv_pairs
            else:
                section["content"] = self._structure_content(text, role)

            if style.get("background_color"):
                section["background_color"] = style["background_color"]
            if style.get("text_color"):
                section["text_color"] = style["text_color"]
            if style.get("bold"):
                section["font_weight"] = "bold"

            sections.append(section)

        # Post-process: merge adjacent body sections if they share a heading pattern
        sections = self._merge_related_sections(sections)

        return sections

    def _classify_block_role(
        self,
        text: str,
        y_fraction: float,
        font_size: float,
        style: Dict[str, Any],
        all_blocks: List[Dict[str, Any]],
        block_index: int,
    ) -> str:
        """Classify a content block's semantic role."""
        text_lower = text.lower().strip()
        is_bold = style.get("bold", False)

        # Title zone (top of slide, large font, bold)
        if y_fraction < self.TITLE_BAND_MAX:
            if font_size > 18 or is_bold:
                return "title"
            return "subtitle"

        # Footer zone (bottom of slide)
        if y_fraction > self.FOOTER_BAND_MIN:
            return "footer"

        # Info cards / metadata row (short label:value pairs near top)
        if y_fraction < self.HEADER_BAND_MAX:
            if ":" in text and len(text) < 200:
                return "metadata_row"
            if is_bold and len(text) < 100:
                return "heading"

        # Detect specific semantic roles from keywords
        if any(kw in text_lower for kw in ("mapped skills", "success indicators")):
            return "skills_panel"
        if any(kw in text_lower for kw in ("learner task", "activity", "task")):
            if is_bold or len(text_lower.split()) < 6:
                return "task_heading"
            return "task_content"
        if any(kw in text_lower for kw in ("workplace context", "scenario")):
            return "context_section"
        if any(kw in text_lower for kw in ("dear ", "sincerely", "regards")):
            return "letter_content"

        # Numbered lists
        if re.match(r'^\d+\.\s', text.strip()):
            return "numbered_list"

        # Bulleted lists
        if text.strip().startswith("•") or text.strip().startswith("-"):
            return "bulleted_list"

        # Heading (bold, short text, not in header/footer)
        if is_bold and len(text.split()) < 8:
            return "heading"

        return "body_section"

    def _extract_key_value_pairs(self, text: str) -> Optional[List[Dict[str, str]]]:
        """Extract label:value pairs from text like 'Unit of Competency: BSBXCM301...'"""
        lines = text.strip().split("\n")
        pairs = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Match "Label:" or "Label: Value"
            match = re.match(r'^([^:]{2,40}):\s*(.*)$', line)
            if match:
                label = match.group(1).strip()
                value = match.group(2).strip()
                pairs.append({"label": label, "value": value})
            else:
                # Not a key-value line — abort if we haven't found any
                if not pairs:
                    return None
                # Append as continuation of last value
                if pairs:
                    pairs[-1]["value"] += " " + line

        return pairs if len(pairs) >= 1 else None

    def _structure_content(
        self, text: str, role: str
    ) -> List[Dict[str, Any]]:
        """Structure text content based on role."""
        items = []
        if role in ("numbered_list", "bulleted_list"):
            for line in text.strip().split("\n"):
                line = line.strip()
                if line:
                    # Strip leading number/bullet
                    clean = re.sub(r'^[\d]+[.\)]\s*', '', line)
                    clean = re.sub(r'^[•\-\*]\s*', '', clean)
                    items.append({"type": "list_item", "text": clean})
        elif role == "letter_content":
            items.append({"type": "letter", "text": text})
        else:
            items.append({"type": "text", "text": text})
        return items

    def _merge_related_sections(
        self, sections: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge a heading section with its immediately following body section."""
        if len(sections) < 2:
            return sections

        merged = []
        skip_next = False

        for i, section in enumerate(sections):
            if skip_next:
                skip_next = False
                continue

            if (
                section["role"] in ("heading", "task_heading")
                and i + 1 < len(sections)
                and sections[i + 1]["role"] in ("body_section", "task_content", "numbered_list", "bulleted_list", "letter_content")
            ):
                # Merge heading with body
                next_sec = sections[i + 1]
                combined = {
                    "id": section["id"],
                    "role": section["role"].replace("_heading", "_section") if "_heading" in section["role"] else "content_section",
                    "heading": section.get("content", [{}])[0].get("text", "") if section.get("content") else "",
                    "position": section["position"],  # Use heading position
                    "content": next_sec.get("content", []),
                    "children": next_sec.get("children"),
                }
                # Preserve styling
                if section.get("background_color"):
                    combined["background_color"] = section["background_color"]
                if next_sec.get("background_color"):
                    combined["background_color"] = next_sec["background_color"]
                merged.append(combined)
                skip_next = True
            else:
                merged.append(section)

        return merged

    # ------------------------------------------------------------------
    # Table extraction
    # ------------------------------------------------------------------

    def _extract_table_sections(
        self, slide: SlideModel, canvas_w: float, canvas_h: float
    ) -> List[Dict[str, Any]]:
        """Extract table elements as structured sections."""
        sections = []
        for element in slide.elements:
            if element.element_type != "table":
                continue

            table_data: Dict[str, Any] = {
                "id": f"table_{element.element_id}",
                "role": "table",
                "position": {
                    "x_pct": round(100 * element.position.x / canvas_w, 1),
                    "y_pct": round(100 * element.position.y / canvas_h, 1),
                    "width_pct": round(100 * element.position.width / canvas_w, 1),
                    "height_pct": round(100 * element.position.height / canvas_h, 1),
                },
            }

            # Include raw table content if available
            if element.raw_table_content:
                table_data["headers"] = element.raw_table_content[0] if element.raw_table_content else []
                table_data["rows"] = element.raw_table_content[1:] if len(element.raw_table_content) > 1 else []
                table_data["dimensions"] = {
                    "rows": len(element.raw_table_content),
                    "columns": len(element.raw_table_content[0]) if element.raw_table_content else 0,
                }

            if element.table_markdown:
                table_data["markdown"] = element.table_markdown

            sections.append(table_data)

        return sections

    # ------------------------------------------------------------------
    # Chart extraction
    # ------------------------------------------------------------------

    def _extract_chart_sections(
        self, slide: SlideModel, canvas_w: float, canvas_h: float
    ) -> List[Dict[str, Any]]:
        """Extract chart understanding data as structured sections."""
        sections = []
        for cu in (slide.chart_understandings or []):
            chart_data: Dict[str, Any] = {
                "id": f"chart_{cu.chart_id}",
                "role": "chart",
                "chart_type": cu.chart_type,
                "title": cu.title,
                "insight": cu.insight,
                "purpose": cu.purpose,
            }
            if cu.categories:
                chart_data["categories"] = cu.categories
            if cu.series:
                chart_data["series"] = [
                    {"name": s.name, "values": s.values, "color": s.color}
                    for s in cu.series
                ]
            if cu.axes:
                chart_data["axes"] = {
                    k: {"label": v.label, "min": v.min, "max": v.max}
                    for k, v in cu.axes.items()
                }
            if cu.legend:
                chart_data["legend"] = cu.legend

            sections.append(chart_data)

        return sections

    # ------------------------------------------------------------------
    # Design token extraction
    # ------------------------------------------------------------------

    def _extract_design_tokens(
        self, slide: SlideModel, canvas_w: float, canvas_h: float
    ) -> Dict[str, Any]:
        """Extract visual design information from the slide."""
        colors: set[str] = set()
        bg_colors: set[str] = set()
        text_colors: set[str] = set()
        border_colors: set[str] = set()
        font_sizes: List[float] = []
        font_names: set[str] = set()
        corner_radii: List[float] = []
        shadows: List[Dict[str, Any]] = []

        if slide.background_color:
            bg_colors.add(slide.background_color)
            colors.add(slide.background_color)

        for element in slide.elements:
            if element.border_radius is not None:
                corner_radii.append(element.border_radius)
            if element.shadow:
                shadows.append(element.shadow)
                
            if element.style:
                if element.style.background_color:
                    bg_colors.add(element.style.background_color)
                    colors.add(element.style.background_color)
                if element.style.text_color:
                    text_colors.add(element.style.text_color)
                    colors.add(element.style.text_color)
                if element.style.border_color:
                    border_colors.add(element.style.border_color)
                if element.style.font_size:
                    font_sizes.append(element.style.font_size)
                if element.style.font_name:
                    font_names.add(element.style.font_name)

        # Color palette from image reconstruction if available
        if slide.image_reconstruction:
            for c in slide.image_reconstruction.color_palette:
                colors.add(c)

        # Deduce primary, secondary, accent colors
        color_list = sorted(list(colors))
        primary_color = color_list[0] if len(color_list) > 0 else "#ffffff"
        secondary_color = color_list[1] if len(color_list) > 1 else "#000000"
        accent_color = color_list[2] if len(color_list) > 2 else (secondary_color if len(color_list) > 1 else "#0000ff")

        # Theme
        def get_luminance(hex_color: str) -> float:
            if not hex_color:
                return 255.0
            hex_color = hex_color.lstrip('#')
            if len(hex_color) == 3:
                hex_color = "".join(c*2 for c in hex_color)
            if len(hex_color) != 6:
                return 255.0
            try:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return 0.299 * r + 0.587 * g + 0.114 * b
            except Exception:
                return 255.0

        bg_col = slide.background_color or (list(bg_colors)[0] if bg_colors else "#ffffff")
        theme = "dark" if get_luminance(bg_col) < 130 else "light"

        # Font hierarchy
        font_hierarchy = {}
        if font_sizes:
            sorted_sizes = sorted(set(font_sizes), reverse=True)
            if len(sorted_sizes) >= 1:
                font_hierarchy["title"] = {"size": sorted_sizes[0]}
            if len(sorted_sizes) >= 2:
                font_hierarchy["heading"] = {"size": sorted_sizes[1]}
            if len(sorted_sizes) >= 3:
                font_hierarchy["body"] = {"size": sorted_sizes[-1]}
        else:
            font_hierarchy = {"title": {"size": 24.0}, "heading": {"size": 18.0}, "body": {"size": 12.0}}

        return {
            "theme": theme,
            "primary_colors": [primary_color],
            "secondary_colors": [secondary_color],
            "accent_colors": [accent_color],
            "background_colors": sorted(list(bg_colors)) if bg_colors else ["#ffffff"],
            "border_colors": sorted(list(border_colors)) if border_colors else ["#000000"],
            "text_colors": sorted(list(text_colors)) if text_colors else ["#000000"],
            "font_families": sorted(list(font_names)) if font_names else ["Arial"],
            "font_hierarchy": font_hierarchy,
            "corner_radius": corner_radii[0] if corner_radii else 0.0,
            "padding": {"left": 20, "top": 15, "right": 20, "bottom": 15},
            "spacing": {"section_gap": 30, "item_gap": 15},
            "shadow_style": shadows[0] if shadows else {"color": "rgba(0,0,0,0.1)", "blur": 4, "offset": 2},
            "icon_style": {"size": 24, "color": accent_color},
            "illustration_style": {"style_type": "flat_vector", "primary_color": accent_color},
            "card_style": {"background_color": list(bg_colors)[0] if bg_colors else "#ffffff", "border_radius": corner_radii[0] if corner_radii else 4.0},
            "button_style": {"background_color": accent_color, "text_color": "#ffffff", "border_radius": 4.0}
        }

    # ------------------------------------------------------------------
    # Verbatim text collection
    # ------------------------------------------------------------------

    def _collect_all_verbatim_text(self, slide: SlideModel) -> List[str]:
        """Collect all readable text from the slide, deduplicated and ordered."""
        texts = []
        seen = set()

        # Prefer text_points (deduplicated and ordered by the extraction pipeline)
        if slide.text_points:
            for tp in slide.text_points:
                text = tp.text.strip()
                if text and text not in seen:
                    seen.add(text)
                    texts.append(text)
        else:
            # Fall back to elements sorted by position
            sorted_elems = sorted(
                slide.elements,
                key=lambda e: (e.position.y, e.position.x),
            )
            for e in sorted_elems:
                text = _text_of(e)
                if text and text not in seen and not _is_garbled(text):
                    seen.add(text)
                    texts.append(text)

        # Also include table content
        for e in slide.elements:
            if e.element_type == "table" and e.raw_table_content:
                for row in e.raw_table_content:
                    for cell in row:
                        cell_text = str(cell).strip()
                        if cell_text and cell_text not in seen:
                            seen.add(cell_text)
                            texts.append(cell_text)

        return texts

    # ------------------------------------------------------------------
    # Reconstruction prompt builder
    # ------------------------------------------------------------------

    def _build_reconstruction_prompt(
        self,
        slide: SlideModel,
        sections: List[Dict[str, Any]],
        design: Dict[str, Any],
        all_text: List[str],
        canvas: Dict[str, Any],
    ) -> str:
        """Build a concise natural-language reconstruction prompt."""
        lines = [
            "You are a slide reconstruction engine. Recreate this slide as a high-fidelity presentation slide.",
            "",
            f"SLIDE TITLE: {slide.title or '(untitled)'}",
            f"CANVAS: {canvas['width']}x{canvas['height']} ({canvas['aspect_ratio']})",
            "",
        ]

        # Design instructions
        bg_color = design.get("background_colors", ["#ffffff"])[0]
        lines.append(f"BACKGROUND: {bg_color}")
        
        all_colors = []
        if design.get("primary_colors"):
            all_colors.extend(design["primary_colors"])
        if design.get("secondary_colors"):
            all_colors.extend(design["secondary_colors"])
        if design.get("accent_colors"):
            all_colors.extend(design["accent_colors"])
        if all_colors:
            lines.append(f"COLOR PALETTE: {', '.join(all_colors[:8])}")
            
        if design.get("font_families"):
            lines.append(f"FONTS: {', '.join(design['font_families'][:4])}")
        lines.append("")

        # Section-by-section layout
        lines.append("LAYOUT (sections from top to bottom):")
        lines.append("")
        for section in sections:
            role = section.get("role", "unknown")
            pos = section.get("position", {})
            pos_str = f"at y={pos.get('y_pct', 0)}%, x={pos.get('x_pct', 0)}%, w={pos.get('width_pct', 0)}%, h={pos.get('height_pct', 0)}%"

            if role == "table":
                dims = section.get("dimensions", {})
                lines.append(f"  [{role.upper()}] {section.get('id', '')} {pos_str}")
                lines.append(f"    Dimensions: {dims.get('rows', 0)} rows x {dims.get('columns', 0)} columns")
                if section.get("markdown"):
                    lines.append(f"    Content:\n{section['markdown']}")
            elif role == "chart":
                lines.append(f"  [{role.upper()}] {section.get('chart_type', 'unknown')} — {section.get('title', 'untitled')}")
                if section.get("insight"):
                    lines.append(f"    Insight: {section['insight']}")
            else:
                lines.append(f"  [{role.upper()}] {pos_str}")
                if section.get("heading"):
                    lines.append(f"    Heading: {section['heading']}")
                if section.get("children"):
                    for child in section["children"]:
                        lines.append(f"    • {child.get('label', '')}: {child.get('value', '')}")
                elif section.get("content"):
                    for item in section["content"]:
                        text = item.get("text", "")
                        if len(text) > 200:
                            text = text[:200] + "…"
                        lines.append(f"    {text}")

            if section.get("background_color"):
                lines.append(f"    Background: {section['background_color']}")
            lines.append("")

        # Verbatim text reference
        lines.append("ALL VERBATIM TEXT (preserve exactly):")
        for t in all_text:
            clean = t.replace("\n", " ").strip()
            if clean:
                lines.append(f"  \"{clean}\"")

        lines.append("")
        lines.append(
            "INSTRUCTIONS & VISUAL RECONSTRUCTION RULES:\n"
            "1. CANVAS SETUP: Initialize a blank canvas matching the CANVAS size (e.g., 1920x1080) and paint the background color or gradient as specified.\n"
            "2. DRAWING ORDER (CRITICAL): Draw visual containers/cards first (fills), then outlines/borders, and finally render text on top. Never draw card background fills after rendering text, as this will obscure/overwrite the text.\n"
            "3. CARD RENDERING: Draw each section container/card with rounded corners based on its position percentages (x_pct, y_pct, width_pct, height_pct) relative to the canvas dimensions, using its specified background_color.\n"
            "4. TEXT FORMATTING & CONTRAST:\n"
            "   - Render text blocks inside their corresponding container bounds.\n"
            "   - Apply contrast-based font colors (e.g., white '#ffffff' text on dark background cards, black '#000000' text on light background cards).\n"
            "   - Wrap text lines to fit cleanly inside the card's width with a padding of at least 20px on the left and right edges.\n"
            "   - Preserve bullet list hierarchy and structure, maintaining uniform indentation.\n"
            "5. POSITION ALIGNMENT: Align the visual layout using the percentage positions to ensure accurate spacing, title placement, and metadata row columns.\n"
            "6. SEMANTIC RESTRUCTURING & REWRITING: You MUST restructure and rewrite every paragraph and sentence in clean, professional English in your own words. Maintain 100% of the original slide's semantic meaning, intent, technical words, facts, and figures. Never shorten, summarize, or invent information.\n"
            "7. COLOR & PAGE STYLE FIDELITY: Ensure the background color, card fills, border colors, and page styles match the exact hex codes specified in the BACKGROUND and COLOR PALETTE section to preserve the visual identity."
        )

        return "\n".join(lines)

    def _build_professional_designer_prompt(
        self,
        slide: SlideModel,
        sections: List[Dict[str, Any]],
        design: Dict[str, Any],
        canvas: Dict[str, Any]
    ) -> str:
        """
        Generate a professional designer description of the slide layout, 
        hierarchy, and style, without containing raw OCR text fragments.
        """
        layout_type = slide.layout_structure.layout_type if slide.layout_structure else "blank"
        theme = design.get("theme", "light")
        bg_color = design.get("background_colors", ["#ffffff"])[0]
        fonts = ", ".join(design.get("font_families", ["Arial"]))
        
        prompt_parts = [
            f"This slide is designed with a professional, modern {theme} theme on a {canvas.get('aspect_ratio', '16:9')} canvas, using a clean {layout_type} layout.",
            f"The canvas size is {canvas.get('width', 1920)}x{canvas.get('height', 1080)} pixels with a primary background color of {bg_color}.",
            f"Typography is established using the {fonts} font family, adhering to a clear typographic hierarchy:",
            f"  - Title font size is {design.get('font_hierarchy', {}).get('title', {}).get('size', 24.0)}pt.",
            f"  - Secondary headings are {design.get('font_hierarchy', {}).get('heading', {}).get('size', 18.0)}pt.",
            f"  - Body text elements are {design.get('font_hierarchy', {}).get('body', {}).get('size', 12.0)}pt.",
            "",
            "VISUAL HIERARCHY & CONTENT LAYOUT:",
        ]

        # Describe the sections in terms of their design cards, tables, and spacing
        for i, s in enumerate(sections):
            role = s.get("role", "unknown")
            pos = s.get("position", {})
            left = pos.get("x_pct", 0)
            top = pos.get("y_pct", 0)
            width = pos.get("width_pct", 0)
            height = pos.get("height_pct", 0)
            bg = s.get("background_color") or "none"
            
            desc = f"- Section {i+1} is a [{role.upper()}] card positioned at top-left ({left}%, {top}%) spanning {width}% width and {height}% height."
            if bg != "none":
                desc += f" It utilizes a background card fill color of {bg} with soft margins and spacing."
                
            if role == "table":
                desc += " This area contains a structured data grid layout with clear borders and rows."
            elif role == "chart":
                desc += f" This is a visual data visualization element (type: {s.get('chart_type', 'chart')}) displaying statistical trends."
            else:
                desc += " It holds structured content paragraphs or lists aligned to the card grid."
                
            prompt_parts.append(desc)

        prompt_parts.extend([
            "",
            "DESIGN TOKENS & VISUAL STYLE:",
            f"- Theme: {theme} mode layout",
            f"- Palette: Primary is {design.get('primary_colors', ['#ffffff'])[0]}, Secondary is {design.get('secondary_colors', ['#000000'])[0]}, Accent is {design.get('accent_colors', ['#0000ff'])[0]}",
            f"- Card Outline/Borders: Corner radius is {design.get('corner_radius', 0.0)} with thin outline borders.",
            f"- Spacing & Padding: Elements are padded internally by 15-20px with standard spacing between logical columns.",
            "- Shadow Style: Subtle blurred card drop-shadows are applied to elevated card layers.",
            "- Icons & Illustrations: Clean, minimalist vector icon styles matching the accent color palette.",
            "- Text Copywriting: Restructure and rewrite every paragraph/sentence in your own words, using clean, professional PowerPoint copy-writing style, while preserving 100% of the original technical meaning, intent, numbers, and facts.",
            "- Color Fidelity: The slide background color, card fills, and border colors must follow the palette and theme tokens precisely to ensure visual identity mapping.",
            "",
            "SEMANTIC PURPOSE:",
            f"Recreate this slide layout structure, preserving the exact visual balance, spacing, shapes, and structural design system to communicate the core theme."
        ])

        return "\n".join(prompt_parts)

    def _rewrite_text_professionally(self, text: str) -> str:
        """
        Polish and rewrite text paragraphs professionally to fix spelling,
        improve clarity, grammar, and flow, while maintaining 100% facts.
        """
        # Since slide elements are already rewritten by SlideRewriterService
        # during slide processing, we can return the text as-is to preserve it.
        return text

    def _extract_process_steps(self, slide: SlideModel) -> List[Dict[str, Any]]:
        """Extract flowchart/process sequences into structured step data (Phase 5)."""
        steps = []
        if not slide.flowchart or not slide.flowchart.is_flowchart:
            return steps
            
        for idx, box in enumerate(slide.flowchart.boxes):
            step_num = idx + 1
            title = box.get("text", f"Step {step_num}")
            title = self._rewrite_text_professionally(title)
            
            steps.append({
                "step_number": step_num,
                "title": title,
                "semantic_description": f"Perform task step described by: {title}.",
                "visual_description": f"Process box shape positioned at x={box.get('x', 0)}, y={box.get('y', 0)}.",
                "icon": "circle" if idx == 0 else "arrow-right",
                "badge": f"Step {step_num}",
                "position": {
                    "x": box.get("x", 0.0),
                    "y": box.get("y", 0.0),
                    "width": box.get("width", 100.0),
                    "height": box.get("height", 50.0)
                },
                "connector": "solid_arrow" if idx > 0 else "none",
                "relationship_to_previous_step": f"Subsequent step to step {idx}" if idx > 0 else "none",
                "relationship_to_next_step": f"Precedent step to step {idx+2}" if idx < len(slide.flowchart.boxes) - 1 else "none"
            })
        return steps
