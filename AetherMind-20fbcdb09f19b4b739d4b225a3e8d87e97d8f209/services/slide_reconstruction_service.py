from __future__ import annotations
import math
from typing import Any, Dict, List, Optional
from models.document_model import SlideModel, SlideReconstructionContextModel
class SlideReconstructionService:
    DEFAULT_WIDTH = 12192000.0
    DEFAULT_HEIGHT = 6858000.0
    def build_context(self, slide: SlideModel, presentation_metadata: Optional[Dict[str, Any]] = None) -> SlideReconstructionContextModel:
        pres_meta = presentation_metadata or {}
        ctx = SlideReconstructionContextModel()
        ctx.title = slide.title or ""
        ctx.slide_type = self._infer_slide_type(slide)
        ctx.purpose = self._infer_purpose(slide)
        ctx.domain = self._infer_domain(slide)
        ctx.design_style = self._detect_design_style(slide)
        ctx.theme = self._infer_theme(slide)
        ctx.mood = self._infer_mood(slide)
        ctx.complexity = self._infer_complexity(slide)
        ctx.category = self._infer_category(slide)
        ctx.background_type = self._detect_background_type(slide)
        colors = self._extract_all_colors(slide)
        if getattr(slide, "background_color", None):
            ctx.primary_color = slide.background_color
            ctx.secondary_color = colors[0] if len(colors) >= 1 else ""
        else:
            ctx.primary_color = colors[0] if len(colors) >= 1 else ""
            ctx.secondary_color = colors[1] if len(colors) >= 2 else ""
        ctx.gradient_direction = ""
        ctx.texture = "none"
        ctx.patterns = "none"
        ctx.effects = "none"
        ctx.title_typography = self._extract_title_typography(slide)
        ctx.body_typography = self._extract_body_typography(slide)
        ctx.typography_color_palette = colors
        ctx.layout_type = (
            slide.layout_structure.layout_type
            if slide.layout_structure
            else "mixed"
        )
        ctx.canvas_ratio = self._compute_canvas_ratio(pres_meta)
        ctx.regions = self._extract_region_names(slide)
        ctx.reading_order = self._extract_reading_order(slide)
        ctx.alignment = self._infer_alignment(slide)
        ctx.spacing = self._infer_spacing(slide)
        hierarchy = self._build_visual_hierarchy(slide)
        ctx.primary_focus = hierarchy.get("primary", "")
        ctx.secondary_focus = hierarchy.get("secondary", "")
        ctx.tertiary_elements = hierarchy.get("tertiary", "")
        ctx.attention_flow = hierarchy.get("attention_flow", "")
        ctx.visual_elements = self._build_visual_elements(slide, pres_meta)
        ctx.image_reconstructions = self._build_image_reconstructions(slide)
        ctx.element_relationships = self._build_relationships(slide)
        ctx.business_message = self._infer_business_message(slide)
        ctx.communication_intent = self._infer_communication_intent(slide)
        ctx.functional_equivalence_requirements = self._derive_functional_equivalence_requirements(slide)
        ctx.layout_pattern = self._detect_layout_pattern(slide)

        # Update SlideModel with these fields too
        slide.business_message = ctx.business_message
        slide.communication_intent = ctx.communication_intent
        slide.slide_purpose = ctx.purpose
        slide.functional_equivalence_requirements = ctx.functional_equivalence_requirements

        from models.document_model import VisualHierarchyModel
        slide.visual_hierarchy = VisualHierarchyModel(
            primary_focus=[ctx.primary_focus] if ctx.primary_focus else [],
            secondary_focus=[ctx.secondary_focus] if ctx.secondary_focus else [],
            tertiary_focus=[ctx.tertiary_elements] if ctx.tertiary_elements else []
        )
        slide.reading_order = ctx.reading_order

        ctx.reconstruction_prompt = self._format_reconstruction_prompt(ctx, slide)

        return ctx

    def _infer_business_message(self, slide: SlideModel) -> str:
        if slide.semantic_flow and slide.semantic_flow.overall_flow:
            return slide.semantic_flow.overall_flow
        if slide.slide_summary:
            return slide.slide_summary.split(".")[0]
        return "Not explicitly stated"

    def _infer_communication_intent(self, slide: SlideModel) -> str:
        if slide.semantic_flow and slide.semantic_flow.slide_intent:
            return slide.semantic_flow.slide_intent
        return self._infer_category(slide)

    def _derive_functional_equivalence_requirements(self, slide: SlideModel) -> List[str]:
        requirements = []
        slide_type = self._infer_slide_type(slide)
        
        if slide_type == "flowchart":
            requirements.append("Maintain the logical process flow and decision branches")
        elif slide_type == "data_table":
            requirements.append("Preserve the tabular structure and data relationships")
        elif slide_type == "chart_slide":
            requirements.append("Retain the visual representation of data trends and comparisons")
            
        if slide.layout_structure and slide.layout_structure.layout_type:
            requirements.append(f"Follow the {slide.layout_structure.layout_type} layout pattern")
            
        if slide.semantic_flow and slide.semantic_flow.reading_order:
            requirements.append("Preserve the specific semantic reading order")
            
        if not requirements:
            requirements.append("Preserve information hierarchy and visual emphasis")
            
        return requirements

    def _detect_layout_pattern(self, slide: SlideModel) -> str:
        if slide.layout_structure and slide.layout_structure.layout_type:
            return slide.layout_structure.layout_type
        return "custom"
    def _infer_slide_type(self, slide: SlideModel) -> str:
        if slide.flowchart and slide.flowchart.is_flowchart:
            return "flowchart"
        if slide.diagram_understanding and slide.diagram_understanding.is_diagram:
            return "diagram"
        inv = slide.visual_inventory
        if inv:
            if inv.image_count > 0 and inv.text_box_count <= 1:
                return "image_slide"
            if inv.table_count > 0:
                return "data_table"
            if inv.chart_count > 0:
                return "chart_slide"
        text_elements = [e for e in slide.elements if e.text]
        if len(text_elements) <= 1:
            return "title_slide"
        return "content_slide"
    def _infer_purpose(self, slide: SlideModel) -> str:
        if slide.flowchart and slide.flowchart.is_flowchart:
            return "Illustrate a process or workflow through connected stages"
        if slide.diagram_understanding and slide.diagram_understanding.is_diagram:
            return "Visualize relationships between concepts or components"
        if slide.slide_summary:
            # Take the first sentence as purpose
            first_sentence = slide.slide_summary.split(".")[0].strip()
            if first_sentence:
                return first_sentence
        return "Present information through visual and textual elements"

    def _infer_domain(self, slide: SlideModel) -> str:
        if slide.semantic_flow and slide.semantic_flow.overall_flow:
            flow = slide.semantic_flow.overall_flow.lower()
            if any(w in flow for w in ("code", "algorithm", "software", "api")):
                return "technology"
            if any(w in flow for w in ("revenue", "market", "business", "sales")):
                return "business"
            if any(w in flow for w in ("research", "study", "data", "analysis")):
                return "academic"
        return "general"

    def _detect_design_style(self, slide: SlideModel) -> str:
        if slide.image_reconstruction:
            return slide.image_reconstruction.design_style or "presentation"
        if slide.image_understanding and slide.image_understanding.visual_design:
            return slide.image_understanding.visual_design.layout_style or "presentation"
        return "presentation"

    def _infer_theme(self, slide: SlideModel) -> str:
        colors = self._extract_all_colors(slide)
        if not colors:
            return "default"
        dark_count = sum(1 for c in colors if self._is_dark_color(c))
        if dark_count > len(colors) / 2:
            return "dark"
        return "light"

    def _infer_mood(self, slide: SlideModel) -> str:
        style = self._detect_design_style(slide)
        if style == "flowchart":
            return "structured, analytical"
        if style == "diagram":
            return "conceptual, educational"
        return "professional, informative"

    def _infer_complexity(self, slide: SlideModel) -> str:
        total = len(slide.elements)
        rel_count = len(slide.relationships)
        if total <= 3 and rel_count == 0:
            return "low"
        if total <= 8 and rel_count <= 3:
            return "medium"
        return "high"

    def _infer_category(self, slide: SlideModel) -> str:
        slide_type = self._infer_slide_type(slide)
        mapping = {
            "title_slide": "introductory",
            "content_slide": "informational",
            "flowchart": "process",
            "diagram": "conceptual",
            "image_slide": "visual",
            "data_table": "data",
            "chart_slide": "analytical",
        }
        return mapping.get(slide_type, "informational")
    def _detect_background_type(self, slide: SlideModel) -> str:
        colors = self._extract_all_colors(slide)
        if len(colors) >= 2:
            return "gradient"
        if len(colors) == 1:
            return "solid"
        return "solid"

    def _extract_title_typography(self, slide: SlideModel) -> str:
        for element in slide.elements:
            if element.text and element.style:
                if element.style.bold or (element.style.font_size and element.style.font_size >= 18):
                    parts = []
                    if element.style.font_name:
                        parts.append(f"font: {element.style.font_name}")
                    if element.style.font_size:
                        parts.append(f"size: {element.style.font_size}pt")
                    if element.style.bold:
                        parts.append("bold")
                    if element.style.text_color:
                        parts.append(f"color: {element.style.text_color}")
                    return ", ".join(parts) if parts else "default title typography"
        return "default title typography"

    def _extract_body_typography(self, slide: SlideModel) -> str:
        body_fonts = []
        for element in slide.elements:
            if not element.style:
                continue
            if element.style.bold and element.style.font_size and element.style.font_size >= 18:
                continue
            if element.style.font_name or element.style.font_size:
                parts = []
                if element.style.font_name:
                    parts.append(f"font: {element.style.font_name}")
                if element.style.font_size:
                    parts.append(f"size: {element.style.font_size}pt")
                if element.style.text_color:
                    parts.append(f"color: {element.style.text_color}")
                if parts:
                    body_fonts.append(", ".join(parts))
                    break
        return body_fonts[0] if body_fonts else "default body typography"

    def _extract_all_colors(self, slide: SlideModel) -> List[str]:
        colors = set()
        for element in slide.elements:
            if element.style:
                if element.style.background_color:
                    colors.add(element.style.background_color)
                if element.style.text_color:
                    colors.add(element.style.text_color)
        return sorted(colors)

    @staticmethod
    def _is_dark_color(hex_color: str) -> bool:
        try:
            hex_str = hex_color.lstrip("#")
            if len(hex_str) != 6:
                return False
            r, g, b = int(hex_str[:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
            luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
            return luminance < 0.5
        except (ValueError, IndexError):
            return False
    def _compute_canvas_ratio(self, pres_meta: Dict[str, Any]) -> str:
        w = pres_meta.get("slide_width", self.DEFAULT_WIDTH)
        h = pres_meta.get("slide_height", self.DEFAULT_HEIGHT)
        if h == 0:
            return "16:9"
        ratio = w / h
        if abs(ratio - 16 / 9) < 0.05:
            return "16:9"
        if abs(ratio - 4 / 3) < 0.05:
            return "4:3"
        if abs(ratio - 16 / 10) < 0.05:
            return "16:10"
        return f"{w:.0f}:{h:.0f}"

    def _extract_region_names(self, slide: SlideModel) -> List[str]:
        if not slide.layout_structure or not slide.layout_structure.regions:
            return []
        return [r.name for r in slide.layout_structure.regions]
    def _extract_reading_order(self, slide: SlideModel) -> List[str]:
        if slide.flowchart and slide.flowchart.reading_order:
            return slide.flowchart.reading_order
        text_elements = [
            e for e in slide.elements if e.text
        ]
        sorted_elements = sorted(
            text_elements,
            key=lambda e: (e.position.y, e.position.x),
        )
        return [e.element_id for e in sorted_elements]

    def _infer_alignment(self, slide: SlideModel) -> str:
        if not slide.elements:
            return "center-aligned"
        x_positions = [e.position.x for e in slide.elements if e.position]
        if not x_positions:
            return "center-aligned"
        avg_x = sum(x_positions) / len(x_positions)
        variance = sum((x - avg_x) ** 2 for x in x_positions) / len(x_positions)
        std_dev = math.sqrt(variance) if variance > 0 else 0
        if std_dev < 500000:
            return "left-aligned"
        return "mixed alignment"

    def _infer_spacing(self, slide: SlideModel) -> str:
        if len(slide.elements) <= 1:
            return "N/A"
        sorted_elems = sorted(slide.elements, key=lambda e: e.position.y)
        gaps = []
        for i in range(1, len(sorted_elems)):
            prev_bottom = sorted_elems[i - 1].position.y + sorted_elems[i - 1].position.height
            curr_top = sorted_elems[i].position.y
            gap = curr_top - prev_bottom
            if gap > 0:
                gaps.append(gap)
        if not gaps:
            return "compact"
        avg_gap = sum(gaps) / len(gaps)
        if avg_gap < 200000:
            return "compact"
        if avg_gap < 600000:
            return "moderate"
        return "spacious"

    def _build_visual_hierarchy(self, slide: SlideModel) -> Dict[str, str]:
        hierarchy: Dict[str, str] = {
            "primary": "",
            "secondary": "",
            "tertiary": "",
            "attention_flow": "",
        }
        if slide.title:
            hierarchy["primary"] = f"Title: {slide.title}"
        non_title_elements = []
        for e in slide.elements:
            if e.text and e.text.strip() != (slide.title or "").strip():
                area = e.position.width * e.position.height
                non_title_elements.append((area, e))

        non_title_elements.sort(key=lambda x: x[0], reverse=True)
        if non_title_elements:
            top_elem = non_title_elements[0][1]
            desc = top_elem.text or top_elem.element_type
            hierarchy["secondary"] = f"{top_elem.element_type}: {desc}"

        if len(non_title_elements) > 1:
            remaining = [f"{e.element_type}({e.element_id})" for _, e in non_title_elements[1:4]]
            hierarchy["tertiary"] = ", ".join(remaining)
        if slide.flowchart and slide.flowchart.reading_order:
            hierarchy["attention_flow"] = " → ".join(slide.flowchart.reading_order)
        else:
            sorted_ids = self._extract_reading_order(slide)
            hierarchy["attention_flow"] = " → ".join(sorted_ids[:6])

        return hierarchy

    def _build_visual_elements(self, slide: SlideModel, pres_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
        width = pres_meta.get("slide_width", self.DEFAULT_WIDTH)
        height = pres_meta.get("slide_height", self.DEFAULT_HEIGHT)
        for e in slide.elements:
            if e.position:
                width = max(width, e.position.x + e.position.width)
                height = max(height, e.position.y + e.position.height)

        elements_list: List[Dict[str, Any]] = []
        for idx, element in enumerate(slide.elements, start=1):
            desc = element.text or element.element_type
            if element.element_type == "image":
                img_sum = element.metadata.get("image_summary") or element.metadata.get("summary")
                if img_sum:
                    desc = img_sum

            left_pct = (element.position.x / width) * 100 if width else 0
            top_pct = (element.position.y / height) * 100 if height else 0
            w_pct = (element.position.width / width) * 100 if width else 0
            h_pct = (element.position.height / height) * 100 if height else 0

            area = element.position.width * element.position.height
            total_area = width * height
            area_ratio = area / total_area if total_area else 0
            if area_ratio > 0.2:
                importance = "high"
            elif area_ratio > 0.05:
                importance = "medium"
            else:
                importance = "low"

            elements_list.append({
                "element_number": idx,
                "type": element.element_type,
                "description": desc.strip().replace("\n", " ") if isinstance(desc, str) else str(desc),
                "position": f"left: {left_pct:.1f}%, top: {top_pct:.1f}%",
                "size": f"width: {w_pct:.1f}%, height: {h_pct:.1f}%",
                "importance": importance,
                "element_id": element.element_id,
                "auto_shape_type": element.metadata.get("auto_shape_type"),
                "border_color": element.metadata.get("border_color"),
                "border_width": element.metadata.get("border_width"),
            })

        return elements_list


    def _build_image_reconstructions(self, slide: SlideModel) -> List[Dict[str, Any]]:
        reconstructions: List[Dict[str, Any]] = []
        img_idx = 0
        for element in slide.elements:
            if element.element_type != "image":
                continue
            img_idx += 1
            img_sum = element.metadata.get("image_summary") or element.metadata.get("summary") or ""
            colors = []
            if element.style:
                if element.style.background_color:
                    colors.append(element.style.background_color)
                if element.style.text_color:
                    colors.append(element.style.text_color)

            reconstructions.append({
                "image_number": img_idx,
                "visual_description": img_sum,
                "illustration_style": "photographic" if not img_sum else "contextual illustration",
                "color_characteristics": ", ".join(colors) if colors else "inherited from slide palette",
                "composition": f"Positioned in the slide layout at element {element.element_id}",
                "objects": img_sum,
                "interactions": "Supports the surrounding textual content",
            })

        return reconstructions

    def _build_relationships(self, slide: SlideModel) -> List[str]:
        relationships: List[str] = []
        for rel in slide.relationships:
            label_str = f" (label: '{rel.label}')" if rel.label else ""
            relationships.append(
                f"{rel.source_element_id} → {rel.target_element_id} "
                f"[{rel.relationship_type}, confidence: {rel.confidence:.2f}]{label_str}"
            )
        return relationships

    def _format_reconstruction_prompt(self, ctx: SlideReconstructionContextModel, slide: Optional[SlideModel] = None) -> str:
        lines: List[str] = []

        lines.append("=" * 50)
        lines.append("SLIDE RECONSTRUCTION CONTEXT")
        lines.append("=" * 50)
        lines.append("")
        lines.append("SLIDE_METADATA")
        lines.append("")
        lines.append(f"Title:")
        lines.append(f"{ctx.title}")
        lines.append("")
        lines.append(f"Slide Type:")
        lines.append(f"{ctx.slide_type}")
        lines.append("")
        if slide and slide.semantic_flow and slide.semantic_flow.slide_intent:
            lines.append(f"Slide Intent:")
            lines.append(f"{slide.semantic_flow.slide_intent}")
            lines.append("")
        if slide and slide.semantic_flow and slide.semantic_flow.storytelling_structure:
            lines.append(f"Storytelling Structure:")
            lines.append(f"{slide.semantic_flow.storytelling_structure}")
            lines.append("")
        lines.append(f"Purpose:")
        lines.append(f"{ctx.purpose}")
        lines.append("")
        lines.append(f"Domain:")
        lines.append(f"{ctx.domain}")
        lines.append("")

        # VISUAL_STYLE
        lines.append("=" * 50)
        lines.append("VISUAL_STYLE")
        lines.append("=" * 50)
        lines.append("")
        lines.append(f"Presentation Theme:")
        lines.append(f"{ctx.theme}")
        lines.append("")
        lines.append(f"Design Style:")
        lines.append(f"{ctx.design_style}")
        lines.append("")
        lines.append(f"Visual Mood:")
        lines.append(f"{ctx.mood}")
        lines.append("")
        lines.append(f"Complexity:")
        lines.append(f"{ctx.complexity}")
        lines.append("")
        lines.append(f"Presentation Category:")
        lines.append(f"{ctx.category}")
        lines.append("")

        # BACKGROUND
        lines.append("=" * 50)
        lines.append("BACKGROUND")
        lines.append("=" * 50)
        lines.append("")
        lines.append(f"Background Type:")
        lines.append(f"{ctx.background_type}")
        lines.append("")
        lines.append(f"Primary Color:")
        lines.append(f"{ctx.primary_color}")
        lines.append("")
        lines.append(f"Secondary Color:")
        lines.append(f"{ctx.secondary_color}")
        lines.append("")
        lines.append(f"Gradient Direction:")
        lines.append(f"{ctx.gradient_direction}")
        lines.append("")
        lines.append(f"Texture:")
        lines.append(f"{ctx.texture}")
        lines.append("")
        lines.append(f"Patterns:")
        lines.append(f"{ctx.patterns}")
        lines.append("")
        lines.append(f"Visual Effects:")
        lines.append(f"{ctx.effects}")
        lines.append("")

        # TYPOGRAPHY
        lines.append("=" * 50)
        lines.append("TYPOGRAPHY")
        lines.append("=" * 50)
        lines.append("")
        lines.append(f"Title Typography:")
        lines.append(f"{ctx.title_typography}")
        lines.append("")
        lines.append(f"Body Typography:")
        lines.append(f"{ctx.body_typography}")
        lines.append("")
        lines.append(f"Color Palette:")
        lines.append(f"{', '.join(ctx.typography_color_palette) if ctx.typography_color_palette else 'default'}")
        lines.append("")
        lines.append("=" * 50)
        lines.append("LAYOUT_STRUCTURE")
        lines.append("=" * 50)
        lines.append("")
        lines.append(f"Layout Type:")
        lines.append(f"{ctx.layout_type}")
        lines.append("")
        lines.append(f"Canvas Ratio:")
        lines.append(f"{ctx.canvas_ratio}")
        lines.append("")
        lines.append(f"Regions:")
        lines.append(f"{', '.join(ctx.regions) if ctx.regions else 'single region'}")
        lines.append("")
        lines.append(f"Reading Order:")
        lines.append(f"{' → '.join(ctx.reading_order) if ctx.reading_order else 'top-to-bottom'}")
        lines.append("")
        lines.append(f"Alignment:")
        lines.append(f"{ctx.alignment}")
        lines.append("")
        lines.append(f"Spacing:")
        lines.append(f"{ctx.spacing}")
        lines.append("")
        lines.append("=" * 50)
        lines.append("VISUAL_HIERARCHY")
        lines.append("=" * 50)
        lines.append("")
        lines.append(f"Primary Focus:")
        lines.append(f"{ctx.primary_focus}")
        lines.append("")
        lines.append(f"Secondary Focus:")
        lines.append(f"{ctx.secondary_focus}")
        lines.append("")
        lines.append(f"Tertiary Elements:")
        lines.append(f"{ctx.tertiary_elements}")
        lines.append("")
        lines.append(f"Attention Flow:")
        lines.append(f"{ctx.attention_flow}")
        lines.append("")
        lines.append("=" * 50)
        lines.append("VISUAL_ELEMENTS")
        lines.append("=" * 50)
        lines.append("")
        for ve in ctx.visual_elements:
            lines.append(f"Element {ve.get('element_number', '?')}:")
            lines.append(f"Type: {ve.get('type', '')}")
            if ve.get("auto_shape_type"):
                lines.append(f"Geometry: {ve.get('auto_shape_type')}")
            lines.append(f"Description: {ve.get('description', '')}")
            lines.append(f"Position: {ve.get('position', '')}")
            lines.append(f"Size: {ve.get('size', '')}")
            if ve.get("border_color"):
                lines.append(f"Border: Color {ve.get('border_color')}, Width {ve.get('border_width', 0)}pt")
            lines.append(f"Importance: {ve.get('importance', '')}")
            lines.append("")


        if ctx.image_reconstructions:
            lines.append("=" * 50)
            lines.append("IMAGE_RECONSTRUCTION")
            lines.append("=" * 50)
            lines.append("")
            for img in ctx.image_reconstructions:
                lines.append(f"Image {img.get('image_number', '?')}:")
                lines.append("")
                lines.append(f"Visual Description:")
                lines.append(f"{img.get('visual_description', '')}")
                lines.append("")
                lines.append(f"Illustration Style:")
                lines.append(f"{img.get('illustration_style', '')}")
                lines.append("")
                lines.append(f"Color Characteristics:")
                lines.append(f"{img.get('color_characteristics', '')}")
                lines.append("")
                lines.append(f"Composition:")
                lines.append(f"{img.get('composition', '')}")
                lines.append("")
                lines.append(f"Objects:")
                lines.append(f"{img.get('objects', '')}")
                lines.append("")
                lines.append(f"Interactions:")
                lines.append(f"{img.get('interactions', '')}")
                lines.append("")

        # Add Chart Specifications for high-fidelity data reconstruction
        if slide and hasattr(slide, "chart_understandings") and slide.chart_understandings:
            lines.append("=" * 50)
            lines.append("CHART_SPECIFICATIONS (1:1 DATA RECONSTRUCTION)")
            lines.append("=" * 50)
            lines.append("")
            for cu in slide.chart_understandings:
                # Find the corresponding element to get the blueprint text
                blueprint_text = "Detailed data available in the Data Stream section."
                for el in slide.elements:
                    if el.element_id == cu.chart_id or el.chart_understanding == cu:
                        recon_data = el.metadata.get("chart_reconstruction")
                        if recon_data and "blueprint_text" in recon_data:
                            blueprint_text = recon_data["blueprint_text"]
                        break
                
                lines.append(f"Chart ID: {cu.chart_id}")
                lines.append(blueprint_text)
                lines.append("-" * 30)
            lines.append("")

        if slide and getattr(slide, "semantic_regions", None):
            lines.append("=" * 50)
            lines.append("SEMANTIC_REGIONS")
            lines.append("=" * 50)
            lines.append("")
            for r in slide.semantic_regions:
                lines.append(f"Region '{r.name}' (Role: {r.semantic_role}):")
                lines.append(f"  Purpose: {r.purpose}")
                lines.append(f"  Contents: {r.contents}")
                lines.append("")

        lines.append("=" * 50)
        lines.append("RELATIONSHIPS")
        lines.append("=" * 50)
        lines.append("")
        lines.append("Element Relationships:")
        lines.append("")
        if ctx.element_relationships:
            for rel in ctx.element_relationships:
                lines.append(f"  {rel}")
        else:
            lines.append("  (no relationships detected)")
        lines.append("")
        lines.append("=" * 50)
        lines.append("RECONSTRUCTION_INSTRUCTIONS")
        lines.append("=" * 50)
        lines.append("")
        lines.append("You are a PowerPoint reconstruction engine.")
        lines.append("Your task is to recreate the slide EXACTLY from the JSON.")
        lines.append("")
        lines.append("CRITICAL RULES:")
        lines.append("1. Never convert charts into tables.")
        lines.append("2. If an element contains chart_type, series, categories, legend, or axis, render it as a chart.")
        lines.append("3. Preserve exact chart type, orientation, grouping, series order, legend order, bar colors, labels, value labels.")
        lines.append("4. For every series use the exact hex color provided.")
        lines.append("5. Maintain original spatial layout: x, y, width, height.")
        lines.append("6. Maintain hierarchy: title, subtitle, narrative text, charts, footer.")
        lines.append("7. Decorative assets must be recreated: icons, illustrations, separators, banners, colored backgrounds.")
        lines.append("8. Charts are first-class objects. They must never be represented as tables unless chart_type explicitly equals 'table'.")
        lines.append("9. Legends must match original colors exactly.")
        lines.append("10. Recreate the slide as a consulting-style Deloitte slide with pixel-level visual fidelity.")
        lines.append("")
        lines.append("Use the image_generation_prompt to generate an image of this slide using DALL-E 3.")
        lines.append("Focus on reproducing the clean layout, colors, and overall visual structure. Do not worry about rendering dense text perfectly, as image generators cannot do this.")

        return "\n".join(lines)
